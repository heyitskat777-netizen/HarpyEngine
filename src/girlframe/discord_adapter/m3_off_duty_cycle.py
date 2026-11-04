"""Private native Off-Duty choices; saved results and human attestations drive controls."""

import asyncio
import json
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_strain_effects import WAIT, DependentForm
from girlframe.discord_adapter.m3_world import coordinates
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import PlayInput, tier
from girlframe.engine.m3_choices import OFF_DUTY
from girlframe.engine.m3_off_duty import HANDLER_SCENES, HandlerContext, RecoveryChoice
from girlframe.engine.m3_world import ClassChange, Movement, directed_steps
from girlframe.engine.m3_world_state import Goal, Gorgon, World
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_play_support import cancel_unrolled, resume
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

YES_NO = (("yes", "Yes"), ("no", "No"))


def one(values: dict[str, Any], key: str) -> str | None:
    return cast(str | None, next(iter(values.get(key, ())), None))


async def open_action(
    interaction: discord.Interaction, service: CycleService, identity: str, action: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.review, viewer, identity)
    own = data["own"]
    sheet = data["sheet"]

    async def change(current: discord.Interaction, method: str, *args: Any) -> str:
        await asyncio.to_thread(
            getattr(service, method),
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            *args,
        )
        return "Saved. Reopen /mission off_duty or /character requests for your next decisions."

    fields: list[Field]
    form: NativeForm
    choices: tuple[tuple[str, str], ...]
    title = "Off-Duty"
    instructions = (
        "Review your choices, then confirm. Saved dice and other players' decisions stay intact."
    )
    if action == "refresh_rewards":
        fields = [Field("confirm", "Confirm", (("yes", "Register current Frame reward tasks"),))]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            from girlframe.services.m3_frame_rewards import RewardService

            await asyncio.to_thread(
                RewardService(service.periods).refresh,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
            )
            return "Current Frame reward tasks refreshed. Reopen Off-Duty."
    elif action == "activate":
        title = "Finish Off-Duty preparation"
        fields = [Field("confirm", "Confirm", (("activate", "Begin the active period"),))]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            return await change(current, "activate")
    elif action == "play":
        if sheet is None:
            raise WorkflowError("Only a current Pilot makes its own Off-Duty Play.")
        if own and own["action_id"]:
            saved = await asyncio.to_thread(service.game.inspect, viewer, own["action_id"])
            if saved["state"] != "aborted":
                await reply(
                    interaction,
                    "Resume the saved roll with /choice resume. It cannot be rolled again.",
                )
                return
            choices = (("resume", "Resume the same saved action"),)
            if saved["receipt"] is None:
                choices += (("cancel", "Cancel the unrolled reservation"),)
            fields = [Field("recovery", "Recover your saved Play", choices)]

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                operation = cancel_unrolled if one(values, "recovery") == "cancel" else resume
                await asyncio.to_thread(
                    operation,
                    service.game,
                    viewer_from_interaction(current),
                    str(current.id),
                    saved["id"],
                    saved["revision"],
                )
                return (
                    "Recovery saved. Reopen Off-Duty or /choice resume; "
                    "existing dice will be preserved."
                )
        else:
            channel = interaction.channel_id
            if channel is None:
                raise WorkflowError("Use the joined scene channel for this Play.")
            scene_info = await asyncio.to_thread(service.game.scene_info, viewer, channel)
            if not scene_info["joined"]:
                raise WorkflowError("Join this scene with /campaign scene_join first.")
            fields = [
                Field("context", "Describe your time at base", paragraph=True),
                Field(
                    "identity",
                    "Optional Identity to mark",
                    tuple(
                        (x["id"], entity_label(x)) for x in sheet["identities"] if not x["marked"]
                    ),
                    0,
                    1,
                    required=False,
                ),
                Field(
                    "gain",
                    "Heat gained if marking an Identity",
                    tuple((str(i), str(i)) for i in range(6)),
                ),
                Field(
                    "share",
                    "Paired Heat given to your Pair",
                    tuple((str(i), str(i)) for i in range(6)),
                ),
                Field("confirm", "Printed trigger", (("yes", "I am spending time at base"),)),
            ]
            fields = [x for x in fields if x.key != "identity" or x.options]
            title = "Go Off-Duty — confirm your Play"
            instructions = (
                "Your current Status sets the modifier. Chat locks before dice are rolled, "
                "then participants make their Tag choices."
            )

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                prepared = PlayInput(
                    play="go_off_duty",
                    off_duty_id=identity,
                    heat=0,
                    trigger_confirmed=True,
                    context=values["context"],
                    identity=one(values, "identity"),
                    gain=int(one(values, "gain") or "0"),
                    pair_share=int(one(values, "share") or "0"),
                )
                await asyncio.to_thread(
                    service.game.begin,
                    viewer_from_interaction(current),
                    str(current.id),
                    channel,
                    sheet["revision"],
                    prepared,
                )
                return (
                    "Play confirmed. Chat locks before dice are rolled. "
                    "Open /choice resume for Tag decisions."
                )
    elif action == "scene":
        if own is None or own["roll"] is None or own["roll"]["stage"] != "choices":
            raise WorkflowError("Finish the saved roll and Tag decisions first.")
        level = tier(own["roll"]["total"])
        choices = tuple((x, x.replace("_", " ").title()) for x in OFF_DUTY[level])
        if level == "mid":
            choices = (("decline", "No optional scene"),) + choices
        participants = tuple(x for x in data["participants"] if x[0] != str(viewer.user_id))
        if level != "mid":
            participants += ((str(data["handler"]), "Handler"),)
        fields = [
            Field("kind", "Choose your scene", choices),
            Field(
                "participants",
                "Other participants",
                participants,
                0,
                len(participants),
                required=False,
            ),
            Field(
                "summary",
                "Brief scene account (if setting a scene)",
                paragraph=True,
                required=False,
            ),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            kind = one(values, "kind")
            members = (viewer.user_id,) + tuple(int(x) for x in values.get("participants", ()))
            return await change(
                current,
                "scene",
                None if kind == "decline" else kind,
                () if kind == "decline" else members,
                values.get("summary", ""),
            )
    elif action.startswith("ack:"):
        selected = action.removeprefix("ack:")
        subject = None if selected == "handler" else int(selected)
        scene = (
            data["handler_scene"]
            if subject is None
            else next((x for x in data["invitations"] if x["owner"] == subject), None)
        )
        if scene is None:
            raise WorkflowError("This scene belongs to other participants.")
        instructions = (
            scene["summary"] + "\nConfirm only your own participation after the scene was played."
        )
        fields = [
            Field("confirm", "Your participation", (("yes", "I confirm my own participation"),))
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            return await change(current, "acknowledge", subject)
    elif action == "recover":
        if sheet is None:
            raise WorkflowError("Recover your own current sheet.")
        fields = [
            Field(
                "embrace",
                "Optional Tag to embrace",
                tuple((x["id"], x["label"]) for x in sheet["tags"]),
                0,
                1,
                required=False,
            ),
            Field(
                "replace",
                "Identity replaced only if at the cap",
                tuple(
                    (x["id"], entity_label(x)) for x in sheet["identities"] if not x["protected"]
                ),
                0,
                1,
                required=False,
            ),
            Field(
                "unmark",
                "Optional marked Identity to unmark",
                tuple(
                    (x["id"], entity_label(x))
                    for x in sheet["identities"]
                    if x["marked"] and x["id"] not in sheet["sedation_locked"]
                ),
                0,
                1,
                required=False,
            ),
            Field("repairs", "Undamage your Assets?", YES_NO),
        ]
        fields = [x for x in fields if x.options]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            return await change(
                current,
                "recover",
                RecoveryChoice(
                    embrace_tag=one(values, "embrace"),
                    replace_identity=one(values, "replace"),
                    unmark_identity=one(values, "unmark"),
                    repair_assets=one(values, "repairs") == "yes",
                ),
            )
    elif action == "handler_scene":
        snapshot = await asyncio.to_thread(WorldService(service.missions).get, viewer, private=True)
        if snapshot["game_revision"] != data["game_revision"] or snapshot["world"] is None:
            raise WorkflowError("Refresh the actual world before setting this scene.")
        world = snapshot["world"]

        def build(values: dict[str, Any]) -> list[Field]:
            fields = [
                Field(
                    "kind",
                    "Handler scene",
                    tuple((x, x.replace("_", " ").title()) for x in HANDLER_SCENES),
                ),
                Field(
                    "participants",
                    "Participating Girls",
                    data["participants"],
                    1,
                    len(data["participants"]),
                ),
            ]
            kind = one(values, "kind")
            members = {data["handler"]} | {int(x) for x in values.get("participants", ())}
            if kind in ("permission", "punish", "exploit"):
                fields.append(
                    Field(
                        "recipient",
                        "Affected Girl",
                        tuple(x for x in data["participants"] if int(x[0]) in members) or WAIT,
                    )
                )
            if kind == "npc_employment":
                targets = tuple(
                    ("npc:" + x["id"], x["name"])
                    for x in world["npcs"]
                    if x["alive"] and x["captive_of"] is None
                )
                fields.append(Field("entity", "Actual NPC", targets or WAIT))
                fields.append(
                    Field(
                        "operation",
                        "Actual interaction",
                        tuple((x, x.title()) for x in ("hire", "fire", "chastise", "request")),
                    )
                )
            elif kind == "prisoner":
                targets = tuple(
                    ("npc:" + x["id"], x["name"])
                    for x in world["npcs"]
                    if x["alive"] and "prisoner" in x["jobs"] and x["captive_of"] is None
                )
                targets += tuple(
                    ("pilot:" + x["id"], x["name"])
                    for x in world["pilots"]
                    if x["alive"]
                    and x["custody"] in ("captured", "transported")
                    and x["custodian"] in members
                )
                fields.append(Field("entity", "Actual current prisoner", targets or WAIT))
            fields.append(Field("summary", "Brief scene account", paragraph=True))
            return fields

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            kind = one(values, "kind")
            selected = (
                one(values, "recipient") if kind in ("permission", "punish", "exploit") else None
            )
            context = (
                HandlerContext(
                    entity=one(values, "entity"),
                    operation=cast(Any, one(values, "operation"))
                    if kind == "npc_employment"
                    else None,
                )
                if kind in ("npc_employment", "prisoner")
                else None
            )
            return await change(
                current,
                "handler_scene",
                kind,
                (data["handler"],) + tuple(int(x) for x in values["participants"]),
                values["summary"],
                int(selected) if selected else None,
                context,
            )

        form = DependentForm(
            viewer.user_id,
            "Set the Handler scene",
            "Select actual participants and targets. The human playing an NPC or prisoner "
            "will also confirm their own participation.",
            build,
            submit,
        )
        await reply(interaction, form.text(), form)
        return
    elif action == "status":
        fields = [
            Field(
                "rank:" + str(i),
                "Status position "
                + str(i + 1)
                + (
                    " — Ace"
                    if i == 0
                    else " — Dog"
                    if i == len(data["participants"]) - 1
                    else " — Wing"
                ),
                data["participants"],
            )
            for i in range(len(data["participants"]))
        ]
        fields.append(Field("account", "Performance review", paragraph=True))

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            return await change(
                current,
                "review_status",
                tuple(
                    int(one(values, "rank:" + str(i)) or "0")
                    for i in range(len(data["participants"]))
                ),
                values["account"],
            )
    elif action == "finish":
        await open_end(interaction, service, data)
        return
    else:
        raise WorkflowError("Reopen the current Off-Duty decisions.")
    form = NativeForm(viewer.user_id, title, instructions, fields, submit)
    await reply(interaction, form.text(), form)


async def open_end(
    interaction: discord.Interaction, service: CycleService, data: dict[str, Any]
) -> None:
    viewer = viewer_from_interaction(interaction)
    snapshot = await asyncio.to_thread(WorldService(service.missions).get, viewer, private=True)
    if snapshot["game_revision"] != data["game_revision"] or snapshot["world"] is None:
        raise WorkflowError("Refresh the actual world and period before ending Off-Duty.")
    world = World.model_validate_json(json.dumps(snapshot["world"]))
    directed = [x for x in world.gorgons if x.alive and x.gorgon_class == "directed"]
    unplaced = [
        x
        for x in world.gorgons
        if x.alive
        and x.gorgon_class == "aggressive"
        and not any(loc.cell == x.cell and loc.condition != "destroyed" for loc in world.locations)
    ]

    def build(values: dict[str, Any]) -> list[Field]:
        fields = [
            Field(
                "step:" + x.id,
                "Move " + x.name,
                tuple(
                    (f"{c[0]},{c[1]}", f"Square {c[0]}, {c[1]}") for c in directed_steps(world, x)
                ),
            )
            for x in directed
        ]
        for old in unplaced:
            key = old.id + ":"
            fields.append(
                Field(
                    key + "class",
                    old.name + " — new Class",
                    tuple(
                        (x, x.title())
                        for x in ("dormant", "erratic", "directed", "sprite", "benevolent")
                    ),
                )
            )
            selected = one(values, key + "class")
            if selected == "directed":
                goals = (
                    tuple(
                        ("location:" + x.id, x.name)
                        for x in world.locations
                        if x.condition != "destroyed"
                    )
                    + tuple(("npc:" + x.id, x.name) for x in world.npcs if x.alive)
                    + (("cell", "Another map square"),)
                )
                fields.append(Field(key + "goal", "Actual goal", goals))
                if one(values, key + "goal") == "cell":
                    fields.append(Field(key + "cell", "Goal square as x,y"))
                fields.append(
                    Field(
                        key + "guard", "Protective Asset", tuple((x.id, x.name) for x in old.assets)
                    )
                )
            elif selected == "sprite":
                leaders = tuple(
                    (x.id, x.name)
                    for x in world.gorgons
                    if x.id != old.id
                    and x.alive
                    and x.gorgon_class != "sprite"
                    and x.types == old.types
                )
                fields.append(
                    Field(key + "leader", "Follow a Gorgon with the same Types", leaders or WAIT)
                )
                fields.append(Field(key + "group", "A group of Sprites?", YES_NO))
            fields.append(Field(key + "account", "Class change account", paragraph=True))
        fields.append(
            Field(
                "confirm",
                "Confirm period end",
                (("yes", "Apply world movement and end the period"),),
            )
        )
        return fields

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        steps = tuple(
            Movement(gorgon=x.id, destination=coordinates(one(values, "step:" + x.id) or ""))
            for x in directed
        )
        changes = []
        for old in unplaced:
            key = old.id + ":"
            selected = one(values, key + "class")
            goal = None
            if selected == "directed":
                target = one(values, key + "goal") or ""
                if target == "cell":
                    goal = Goal(kind="cell", cell=coordinates(values[key + "cell"]))
                else:
                    kind, entity = target.split(":", 1)
                    goal = Goal.model_validate_json(json.dumps({"kind": kind, "entity_id": entity}))
            replacement = Gorgon.model_validate_json(
                old.model_copy(
                    update={
                        "gorgon_class": selected,
                        "goal": goal,
                        "protected_asset": one(values, key + "guard")
                        if selected == "directed"
                        else None,
                        "follows": one(values, key + "leader") if selected == "sprite" else None,
                        "sprite_group": selected == "sprite"
                        and one(values, key + "group") == "yes",
                    }
                ).model_dump_json()
            )
            changes.append(
                ClassChange(gorgon=old.id, replacement=replacement, account=values[key + "account"])
            )
        result = await asyncio.to_thread(
            service.finish,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            data["game_revision"],
            steps,
            tuple(changes),
        )
        return (
            "Off-Duty completed."
            if result["phase"] == "complete"
            else "World effects saved. Required consequences remain; reopen Off-Duty."
        )

    form = DependentForm(
        viewer.user_id,
        "End Off-Duty",
        "Review the Directed movement and Aggressive consequences. Each is applied once.",
        build,
        submit,
    )
    await reply(interaction, form.text(), form)
