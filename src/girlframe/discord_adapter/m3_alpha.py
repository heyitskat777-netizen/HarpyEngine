"""Real asset damage and owned counter-Play controls for Brutalize."""

import asyncio
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService


async def open_alpha_choice(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    if data["kind"].startswith("battle_"):
        from girlframe.discord_adapter.m3_battle import open_battle

        await open_battle(interaction, game, identity)
        return
    detail = data["alpha"]
    if data["kind"] == "alpha_counter_play" and detail.get("npc"):
        from girlframe.discord_adapter.m3_npc_guard import open_counter
        from girlframe.services.m3_npc_guard import GuardService

        await open_counter(interaction, GuardService(game), data["parent"], identity)
        return
    if data["kind"] == "alpha_damage":
        fields = [
            Field(
                "asset",
                "Damage one actual Girl Asset",
                tuple((x["id"], x["label"]) for x in detail["assets"]),
            )
        ]
        text = (
            "The actual selected Girl Asset is damaged. "
            "This result also applies Broken or Helpless."
        )
    elif data["kind"] == "alpha_npc_damage":
        high = data["result"]["tier"] == "high"
        fields = (
            [
                Field(
                    "effect",
                    "The printed high result",
                    (("kill", "Apply this rolled NPC death"),),
                )
            ]
            if high
            else [Field("injury", "The actual injury you inflict", paragraph=True)]
        )
        text = (
            "The actual NPC is killed."
            if high
            else ("Describe the actual injury. This NPC also becomes Broken relative to you.")
        )
    elif data["kind"] == "alpha_npc_mercy":
        fields = [
            Field(
                "choice",
                "Actually reviewed unarmed NPC",
                (
                    ("spare", "Spare the NPC"),
                    ("kill", "Kill the unarmed NPC anyway"),
                ),
            )
        ]
        text = (
            "Their actual one counter opportunity has ended. Choose the printed optional outcome."
        )
    elif data["kind"] == "alpha_low":
        options = [("pass", "Pass this one opportunity")]
        if detail["can_counter"]:
            play = "a printed Guard Play" if detail.get("npc") else "a supported Play"
            options.extend(
                (
                    ("counter_broken", "Make " + play + "; then leave them Broken"),
                    ("counter_only", "Make " + play + " without Broken"),
                )
            )
        fields = [Field("choice", "Your actual counter opportunity", tuple(options))]
        text = (
            "The supported counter is a real owned Play against this pressure. "
            "No effect applies before it completes."
        )
    else:
        sheet = await asyncio.to_thread(game.sheet, viewer)
        from girlframe.discord_adapter.m3_dampener import fields as dampener_fields
        from girlframe.discord_adapter.m3_dampener import modifier as dampener_modifier
        from girlframe.services.m3_dampener import DampenerService

        dampener_controls = await dampener_fields(interaction, DampenerService(game))
        from girlframe.discord_adapter.m3_nightmare import keep_heat, keep_info
        from girlframe.services.m3_nightmare import NightmareService

        nightmare = await keep_info(interaction, NightmareService(game))
        available = sheet["heat"]
        counter_options = tuple(
            (play, label)
            for play, label in (
                ("keep_your_head", "Keep Your Head"),
                ("flirt", "Flirt with the original Alpha"),
                ("put_someone_beneath_you", "Put the original Alpha Beneath You"),
                ("old_dog_new_pups", "Old Dog, New Pups: advise the original Alpha"),
                ("brutalize", "Own Brutalize against the original Alpha"),
                ("dose_up", "Own Stim self-Dose Up in this opportunity"),
                ("easy_target", "Own Newgirl Easy Target: your actual mistake"),
                ("unassuming_doll", "Own Vatgrown Doll: fade before the original Alpha"),
            )
            if play in detail.get("counter_plays", ("keep_your_head",))
        )
        own_recipe = len(counter_options) > 1
        marked_recipes = tuple(
            play
            for play, _ in counter_options
            if play
            in (
                "brutalize",
                "unassuming_doll",
                "easy_target",
                "old_dog_new_pups",
                "dose_up",
                "flirt",
                "put_someone_beneath_you",
            )
            or play == "keep_your_head"
            and not nightmare
            and detail["actor"]["kind"] == "pilot"
        )
        disposable_counter = sheet["girl"] == "STIM-BLISSED" and "dose_up" in marked_recipes
        mark_label = "/".join(
            {
                "keep_your_head": "Keep",
                "flirt": "Flirt",
                "put_someone_beneath_you": "Beneath",
                "brutalize": "Brutalize",
                "unassuming_doll": "Doll",
                "easy_target": "Easy Target",
                "old_dog_new_pups": "Advice",
                "dose_up": "Self-Dose",
            }[play]
            for play in marked_recipes
        )
        fields = [
            Field("context", "Your actual counter under this pressure", paragraph=True),
            Field(
                "heat",
                "Heat to spend",
                tuple(
                    (str(n), str(n))
                    for n in (
                        range(available + (8 if disposable_counter else 6 if marked_recipes else 1))
                        if marked_recipes or own_recipe
                        else keep_heat(nightmare, available)
                    )
                ),
            ),
        ]
        text = (
            "Make the actual source-bound Keep Your Head counter. "
            "Its roll and required choices must finish."
        )
        if own_recipe:
            fields.insert(
                0,
                Field(
                    "play",
                    "Your actual counter Play",
                    counter_options,
                ),
            )
            text = (
                "Choose your own actual counter against the original Alpha. "
                "Its real costs, result choices and required consequences must finish."
            )
        if marked_recipes:
            identities = [
                x
                for x in sheet["identities"] + sheet.get("additional_identities", [])
                if not x["marked"]
            ]
            fields.extend(
                [
                    Field(
                        "identity",
                        mark_label + " only: optional owned Identity to mark",
                        tuple((x["id"], x["name"]) for x in identities),
                        minimum=0,
                        required=False,
                    ),
                    Field(
                        "gain",
                        mark_label + " Identity Heat gained; 0 without marking",
                        tuple((str(x), str(x)) for x in range(6)),
                    ),
                ]
            )
        if "put_someone_beneath_you" in dict(counter_options):
            fields.append(
                Field(
                    "piloting",
                    "Beneath only: are you actually piloting your Frame?",
                    (("no", "No"), ("yes", "Yes")),
                    required=False,
                )
            )
        if disposable_counter:
            fields.append(
                Field(
                    "disposable_heat",
                    "Self-Dose only: optional owned Identity removal",
                    (
                        ("0", "Keep the marked Identity"),
                        ("3", "Remove it: 3 extra Heat"),
                        ("4", "Remove it: 4 extra Heat"),
                    ),
                    required=False,
                )
            )
            text += (
                " Self-Dose may remove the marked Identity for 3 or 4 additional Heat. "
                "Any required Feedback retains that removal and Heat commitment before rolling."
            )
        if nightmare:
            text += (
                " Nightmare Core Keep uses Void Assets and no Heat; own recipes use actual Heat."
            )
        fields.extend(dampener_controls)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if data["kind"] == "alpha_counter_play":
            marked = values.get("identity", ())
            gain = int(values.get("gain", ("0",))[0])
            piloting = next(iter(values.get("piloting", ())), "no") == "yes"
            if piloting and values.get("play") != ("put_someone_beneath_you",):
                from girlframe.services.onboarding import WorkflowError

                raise WorkflowError(
                    "Use this Frame occupancy control only for your Beneath counter"
                )
            disposable_heat = int(next(iter(values.get("disposable_heat", ())), "0"))
            if disposable_heat and (
                not disposable_counter
                or values.get("play", ("keep_your_head",))[0] != "dose_up"
                or not marked
            ):
                from girlframe.services.onboarding import WorkflowError

                raise WorkflowError(
                    "Use this removal only with your own self-Dose counter and selected Identity"
                )
            if (marked or gain) and values.get("play", ("keep_your_head",))[
                0
            ] not in marked_recipes:
                from girlframe.services.onboarding import WorkflowError

                raise WorkflowError(
                    "Use these owned Identity controls only with your available "
                    "Keep, Flirt, Beneath, Brutalize, Doll, Easy Target, advice or self-Dose"
                )
            result = await asyncio.to_thread(
                game.begin,
                viewer_from_interaction(current),
                str(current.id),
                data["channel"],
                sheet["revision"],
                PlayInput(
                    play=values.get("play", ("keep_your_head",))[0],
                    target=(
                        int(detail["actor"]["entity"])
                        if values.get("play")
                        in (("old_dog_new_pups",), ("flirt",), ("put_someone_beneath_you",))
                        else None
                    ),
                    target_actor=(
                        ActorRef.model_validate(detail["actor"])
                        if values.get("play") in (("brutalize",), ("unassuming_doll",))
                        else None
                    ),
                    identity=marked[0] if marked else None,
                    gain=gain,
                    disposable_heat=cast(Literal[0, 3, 4], disposable_heat),
                    heat=int(values["heat"][0]),
                    piloting=piloting,
                    dampener_modifier=dampener_modifier(values),
                    context=values["context"],
                    trigger_confirmed=True,
                    parent=data["parent"],
                ),
            )
            return (
                "Actual counter prepared. Continue its owned choices after chat lock confirmation. "
                + str(result["action_id"])
            )
        if data["kind"] == "alpha_npc_damage":
            response = ChoiceAnswer(
                options=("kill" if high else "injure",), text="" if high else values["injury"]
            )
        else:
            choice = values["asset"][0] if data["kind"] == "alpha_damage" else values["choice"][0]
            response = ChoiceAnswer(options=(choice,))
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            response,
        )
        return "Your actual Brutalize response is saved. Immediate consequences remain required."

    form = NativeForm(
        viewer.user_id,
        "Brutalize — owned response",
        text,
        fields,
        submit,
        # Identity marking is optional. Existing Heat requires no new gain;
        # show that actual zero commitment in review without forcing another pick.
        values={"gain": ("0",)} if data["kind"] == "alpha_counter_play" else None,
    )
    await reply(interaction, form.text(), form)
