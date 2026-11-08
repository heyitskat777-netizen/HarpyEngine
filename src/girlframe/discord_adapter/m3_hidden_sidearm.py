"""Actual concealed sidearm source controls and original target's reconsideration."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_hidden_sidearm import HiddenSidearmService


async def open_response(
    interaction: discord.Interaction, service: HiddenSidearmService, choice_id: str
) -> None:
    data = await asyncio.to_thread(
        service.game.decision, viewer_from_interaction(interaction), choice_id
    )
    source = data["sidearm"]

    async def answer(current: discord.Interaction, values: dict[str, Any]) -> str:
        fields = {}
        if values["response"] == ("continue",) and values.get("asset"):
            fields["asset"] = values["asset"][0]
        await asyncio.to_thread(
            service.game.respond,
            viewer_from_interaction(current),
            str(current.id),
            choice_id,
            data["revision"],
            ChoiceAnswer(options=values["response"], fields=fields, text=values["account"]),
        )
        return (
            "Actual response and its real withdrawal or shot saved. Resume the original action "
            "only if it remains possible."
        )

    await NativeForm(
        interaction.user.id,
        "Actually reconsider the revealed gun",
        "The original Handler has revealed its actual gun and paused this unrolled action. "
        "Withdraw that action, or continue and take one ordinary shot to your chosen Girl "
        "Asset. This is not automatic death; losing your last usable Girl Asset outside your "
        "Frame makes you Helpless.",
        [
            Field(
                "response",
                "Actual original action",
                (
                    ("reconsider", "Reconsider and withdraw the original action"),
                    ("continue", "Continue and take the actual shot"),
                ),
            ),
            Field(
                "asset",
                "Your intact Girl Asset (required if continuing)",
                tuple((x["id"], clean(x["name"])) for x in source["assets"]),
                0,
                1,
                required=False,
            ),
            Field("account", "What you actually do", paragraph=True),
        ],
        answer,
    ).present(interaction)


async def open_sidearm(
    interaction: discord.Interaction, service: HiddenSidearmService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "reveal":
        body = data["body"]
        await reply(
            interaction,
            "Actual sidearm outcome: "
            + body["phase"]
            + ".\n"
            + clean(body["account"])
            + ("\n" + clean(body["response"]) if body["response"] else "")
            + ("\nActual original career archive: " + body["archive"] if body["archive"] else ""),
        )
        return
    if data["acquisition"] is None:
        if not data["awards"]:
            await reply(interaction, "A genuine held advancement is needed for Hidden Sidearm.")
            return

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                values["award"][0],
                data["revision"],
                values["account"],
                actual=values["actual"] == ("actual",),
            )
            return "Actual personal concealed sidearm acquired once. Reopen its History card."

        await NativeForm(
            interaction.user.id,
            "Acquire Hidden Sidearm",
            "Spend one held advancement. Record your actual ordinary gun beneath your coat; "
            "this creates no weapon Asset, extra fee, ammunition count or automatic recharge.",
            [
                Field(
                    "award",
                    "Actual held advancement",
                    tuple((x["id"], clean(x["label"])[:100]) for x in data["awards"]),
                ),
                Field(
                    "actual",
                    "Actual concealed ordinary gun",
                    (("actual", "My actual gun is concealed beneath my actual coat"),),
                ),
                Field("account", "Actual personal gun and concealment", paragraph=True),
            ],
            buy,
        ).present(interaction)
        return
    if not data["concealed"]:

        async def conceal(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.conceal,
                viewer_from_interaction(current),
                str(current.id),
                data["acquisition"],
                data["revision"],
                values["account"],
                actual=values["actual"] == ("actual",),
            )
            return "Actual concealment recorded. No prior outcome or quota was reset."

        await NativeForm(
            interaction.user.id,
            "Actual new concealment",
            "The prior reveal stays revealed. Record this only after the same actual gun is "
            "genuinely concealed beneath your coat again.",
            [
                Field(
                    "actual",
                    "Actual concealment",
                    (("actual", "I have actually concealed it beneath my coat again"),),
                ),
                Field("account", "What actually happened", paragraph=True),
            ],
            conceal,
        ).present(interaction)
        return
    if not data["scenes"] or not data["targets"]:
        await reply(
            interaction,
            "Join a real scene as your original physical Handler body with the actual "
            "out-of-Frame Girl. A facilitator slot supplies no body.",
        )
        return

    async def reveal(current: discord.Interaction, values: dict[str, Any]) -> str:
        target = ActorRef.model_validate(
            next(
                x["ref"]
                for x in data["targets"]
                if ActorRef.model_validate(x["ref"]).token == values["target"][0]
            )
        )
        action = (values.get("action") or (None,))[0]
        await asyncio.to_thread(
            service.reveal,
            viewer_from_interaction(current),
            str(current.id),
            data["acquisition"],
            data["revision"],
            int(values["scene"][0]),
            target,
            values["choice"][0],
            values["account"],
            actual=values["actual"] == ("actual",),
            action_id=action,
        )
        return (
            "Actual concealed reveal and its source effect saved. Owned original responses appear "
            "in Inbox."
        )

    await NativeForm(
        interaction.user.id,
        "Reveal the actual concealed sidearm",
        "Choose one printed effect. Pause requires the actual unrolled go-after action. "
        "Actual initial Handler presence can be recorded here; a known conflicting position "
        "requires genuine movement.",
        [
            Field(
                "scene",
                "Actual source scene",
                tuple((str(x["channel"]), "Scene " + str(x["channel"])) for x in data["scenes"]),
            ),
            Field(
                "target",
                "Actual native Girl",
                tuple(
                    (ActorRef.model_validate(x["ref"]).token, clean(x["label"]))
                    for x in data["targets"]
                ),
            ),
            Field(
                "choice",
                "One actual revealed-gun effect",
                (
                    ("helpless", "Turn the tables: render the target Helpless"),
                    ("kill", "Shoot immediately, killing the target"),
                    ("pause", "Pause the real action to reconsider; shoot if it continues"),
                ),
            ),
            Field(
                "action",
                "Exact unrolled interruption (required for pause)",
                tuple((x["id"], x["id"]) for x in data["actions"]),
                0,
                1,
                required=False,
            ),
            Field(
                "actual",
                "Actual presence and reach",
                (("actual", "My original body is actually here and this gun is truly in reach"),),
            ),
            Field("account", "Actual concealed reveal and circumstances", paragraph=True),
        ],
        reveal,
    ).present(interaction)
