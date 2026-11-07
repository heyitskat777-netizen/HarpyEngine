"""Actual prisoner execution, owned Rebel inventory and ordinary Tag resolution controls."""

import asyncio
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, IdentityState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_reign_terror import ReignTerrorService


async def open_resolution(
    interaction: discord.Interaction, service: ReignTerrorService, choice_id: str
) -> None:
    data = await asyncio.to_thread(
        service.game.decision, viewer_from_interaction(interaction), choice_id
    )
    actual = data["reign"]

    async def answer(current: discord.Interaction, values: dict[str, Any]) -> str:
        fields = {}
        if values["choice"] == ("embrace",) and values.get("replace"):
            fields["replace"] = values["replace"][0]
        await asyncio.to_thread(
            service.game.respond,
            viewer_from_interaction(current),
            str(current.id),
            choice_id,
            data["revision"],
            ChoiceAnswer(options=values["choice"], fields=fields),
        )
        return (
            "Actual Rebel Girl Tag resolved into its owned Identity or owed real rejection action."
        )

    await NativeForm(
        interaction.user.id,
        "Your actual Rebel Girl's marked Tag",
        "This is the actual external Rebel Girl's resource, separate from your other "
        "characters. Embrace into a real Identity slot, or take real action to reject it at "
        "the next opportunity.",
        [
            Field(
                "choice",
                "Actual ordinary Tag response",
                (
                    ("embrace", "Embrace into an actual Identity"),
                    ("reject", "Take actual action to reject the Tag"),
                ),
            ),
            Field(
                "replace",
                "Actual owned Identity to replace at capacity",
                tuple((x["id"], clean(x["name"])[:100]) for x in actual["identities"]),
                0,
                1,
                required=False,
            ),
        ],
        answer,
    ).present(interaction)


async def open_terror(
    interaction: discord.Interaction, service: ReignTerrorService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "inventory":
        if data["known"]:
            await reply(
                interaction,
                "This original Rebel Girl's actual inventory is already recorded; it cannot "
                "be reset here.",
            )
            return

        async def inventory(current: discord.Interaction, values: dict[str, Any]) -> str:
            identities = tuple(
                IdentityState(
                    id=str(uuid4()),
                    name=values["identity" + str(index)].strip(),
                    slot=index,
                    marked=str(index) in values.get("marked", ()),
                )
                for index in range(4)
                if values.get("identity" + str(index), "").strip()
            )
            await asyncio.to_thread(
                ActorService(MissionService(service.store)).confirm_rebel_inventory,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                ActorRef.model_validate(data["actor"]),
                identities,
                int(values["heat"]),
                values["account"],
                actual=values["actual"] == ("actual",),
            )
            return "Your actual Rebel Girl's previously unknown current inventory is saved once."

        fields = [
            Field(
                "identity" + str(index),
                "Actual current Identity in slot " + str(index + 1),
                required=False,
            )
            for index in range(4)
        ]
        fields += [
            Field(
                "marked",
                "Which actual Identity slots are currently marked",
                tuple((str(x), "Slot " + str(x + 1)) for x in range(4)),
                0,
                4,
                required=False,
            ),
            Field("heat", "Actual current Heat"),
            Field(
                "actual",
                "Actual inventory confirmation",
                (
                    (
                        "actual",
                        "These are my actual current resources, not a reset or invented defaults",
                    ),
                ),
            ),
            Field("account", "Actual current inventory provenance", paragraph=True),
        ]
        await NativeForm(
            interaction.user.id,
            "Actual Rebel Girl — " + clean(data["label"]),
            "Only this actual person's human controller records its unknown inventory. Empty "
            "slots stay empty; no new resources or default playbook identities are supplied.",
            fields,
            inventory,
        ).present(interaction)
        return
    if data["kind"] == "tag":
        body = data["body"]
        if body["phase"] != "reject_pending":
            await reply(interaction, "Actual enemy Girl Tag: " + body["phase"])
            return

        async def reject(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.reject,
                viewer_from_interaction(current),
                str(current.id),
                body["id"],
                data["revision"],
                int(values["channel"][0]),
                values["account"],
                actual=values["actual"] == ("actual",),
            )
            return "Actual owned rejection action started with its real scene lock: " + str(
                result["action_id"]
            )

        await NativeForm(
            interaction.user.id,
            "Act to reject your Rebel Girl's Tag",
            "Describe what your actual Rebel Girl does to reject this source Tag. This "
            "starts its real action; it does not acknowledge a task or use your human "
            "account's other Girl.",
            [
                Field(
                    "channel",
                    "Actual scene containing your Rebel Girl",
                    tuple((str(x), "Scene " + str(x)) for x in data["channels"]),
                ),
                Field(
                    "actual",
                    "Actual action",
                    (("actual", "My actual original Rebel Girl performs this rejection action"),),
                ),
                Field("account", "What it actually does", paragraph=True),
            ],
            reject,
        ).present(interaction)
        return
    if data["kind"] == "execution":
        body = data["body"]
        await reply(
            interaction,
            "Actual prisoner execution: "
            + body["choice"]
            + ".\n"
            + clean(body["account"])
            + ("\nActual Rebel Group: " + body["group"] if body["group"] else ""),
        )
        return
    if data["acquisition"] is None:
        if not data["awards"]:
            await reply(
                interaction, "One genuine held advancement is required for Reign of Terror."
            )
            return

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                values["award"][0],
                data["revision"],
                values["account"],
            )
            return "Reign of Terror acquired. Its real execution control is in History."

        await NativeForm(
            interaction.user.id,
            "Acquire Reign of Terror",
            "Spend one actual held advancement. This does not execute anyone by itself.",
            [
                Field(
                    "award",
                    "Actual held award",
                    tuple((x["id"], clean(x["label"])[:100]) for x in data["awards"]),
                ),
                Field("account", "Actual acquisition", paragraph=True),
            ],
            buy,
        ).present(interaction)
        return
    if not data["prisoners"]:
        await reply(
            interaction,
            "No actual living server-proved Foundation prisoner is available. Owned unknown "
            "Rebel inventories can be opened from History.",
        )
        return

    async def execute(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected = (values.get("girl") or (None,))[0]
        target = (
            ActorRef.model_validate(
                next(
                    x["ref"]
                    for x in data["girls"]
                    if ActorRef.model_validate(x["ref"]).token == selected
                )
            )
            if selected
            else None
        )
        await asyncio.to_thread(
            service.execute,
            viewer_from_interaction(current),
            str(current.id),
            data["acquisition"],
            data["revision"],
            values["prisoner"][0],
            values["choice"][0],
            values["account"],
            actual=values["actual"] == ("actual",),
            target=target,
            label=values.get("label", ""),
        )
        return "Actual prisoner executed once and the single selected real effect saved."

    await NativeForm(
        interaction.user.id,
        "Actually execute a prisoner",
        "Execute a real prisoner and choose one printed effect. This is an actual NPC death, "
        "never the human controller's Girl. Known physical conflicts require genuine "
        "movement.",
        [
            Field(
                "prisoner",
                "Actual Foundation prisoner",
                tuple((x["id"], clean(x["label"])[:100]) for x in data["prisoners"]),
            ),
            Field(
                "choice",
                "One actual effect",
                (
                    ("rebellion_low", "Reduce Rebellion Strain to Low"),
                    ("underfunded", "Make its actual Rebel Group Underfunded"),
                    ("girl_tag", "Inflict an ordinary Tag on my Girl"),
                ),
            ),
            Field(
                "girl",
                "Actual own Girl for the Tag choice",
                tuple(
                    (ActorRef.model_validate(x["ref"]).token, clean(x["label"]))
                    for x in data["girls"]
                ),
                0,
                1,
                required=False,
            ),
            Field("label", "Human-authored Tag (Tag choice only)", required=False),
            Field(
                "actual",
                "Actual execution and co-presence",
                (("actual", "My original Handler actually executes this real prisoner here"),),
            ),
            Field("account", "Actual execution and selected effect", paragraph=True),
        ],
        execute,
    ).present(interaction)
