"""Private dropdown exchange planning, actual recipient consent and explicit payment."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.creation import AssetChoice
from girlframe.engine.fanbase import DEMOGRAPHICS, QUALITIES, Fanbase
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_swap_state import Selection
from girlframe.engine.shared_setup import AM_ROLES
from girlframe.services.m3_frame_swap import FrameSwapService


async def open_swap(interaction: discord.Interaction, service: FrameSwapService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.choices, viewer)
    if not data["frames"] or not data["retained_rules"]:
        await reply(
            interaction,
            "Frame Swap needs a complete reviewed destination baseline and "
            "one actually held rule whose retained runtime works. "
            "Unavailable rules stay excluded; no Permissions have been spent.",
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str:
        saved = await asyncio.to_thread(
            service.create, viewer_from_interaction(current), str(current.id), values["frame"][0]
        )
        return (
            "Unpaid exchange plan saved. Reopen its request in your inbox to configure it. "
            + str(saved["id"])
        )

    form = NativeForm(
        viewer.user_id,
        "Plan optional Frame Swap",
        "This saves a plan without charging. The completed exchange costs four Permissions.",
        [
            Field(
                "frame",
                "New source-supported Frame playbook",
                tuple((x, x) for x in data["frames"]),
            )
        ],
        choose,
    )
    await reply(interaction, form.text(), form)


async def configure(
    interaction: discord.Interaction, service: FrameSwapService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if not data["own"]:
        raise ValueError("Only the actual original buyer configures this exchange")
    source_labels = {
        x["rule"]: x["label"] + " · " + x["receipt"][:8] for x in data.get("class_sources", [])
    }
    fields = [
        Field(
            "keep_asset",
            "Keep one actual old Frame Asset",
            tuple((x["id"], x["name"]) for x in data["assets"]),
        ),
        Field(
            "keep_rule",
            "Keep one actual supported old Frame rule",
            tuple(
                (x, source_labels.get(x, x.rsplit(".", 1)[-1].replace("-", " ")))
                for x in data["rules"]
            ),
        ),
        Field(
            "assets",
            "Choose two new starting Frame Assets",
            tuple((str(i), x) for i, x in enumerate(data["starting"])),
            minimum=2,
            maximum=2,
        ),
        Field("first_description", "Describe first selected new Asset", paragraph=True),
        Field("second_description", "Describe second selected new Asset", paragraph=True),
        Field("name", "New Frame name"),
        Field("appearance", "New Frame appearance", paragraph=True),
        Field("account", "Describe your actual exchange", paragraph=True),
    ]
    if data["frame"] == "THE PRINCE":
        fields += [
            Field(
                "demographics",
                "Two Fanbase demographics",
                tuple((x, x) for x in DEMOGRAPHICS),
                minimum=2,
                maximum=2,
            ),
            Field(
                "demanded",
                "Two demanded qualities",
                tuple((x, x) for x in QUALITIES),
                minimum=2,
                maximum=2,
            ),
            Field(
                "rejected",
                "Two rejected qualities",
                tuple((x, x) for x in QUALITIES),
                minimum=2,
                maximum=2,
            ),
        ]
    elif data["frame"] == "THE RED QUEEN":
        fields += [
            Field("court_role", "External fifth AM role", tuple((x, x) for x in AM_ROLES)),
            Field(
                "court_target",
                "Actual other Girl receiving the AM",
                tuple((str(i), x["label"]) for i, x in enumerate(data["people"])),
            ),
        ]
    values: dict[str, Any] = {}
    saved = data["selection"]
    if saved:
        values.update(
            keep_asset=(saved["retained_asset"],),
            keep_rule=(saved["retained_rule"],),
            assets=tuple(str(data["starting"].index(x["name"])) for x in saved["assets"]),
            first_description=saved["assets"][0]["description"],
            second_description=saved["assets"][1]["description"],
            name=saved["name"],
            appearance=saved["appearance"],
            account=saved["account"],
        )
        if saved["fanbase"]:
            values.update(
                {k: tuple(saved["fanbase"][k]) for k in ("demographics", "demanded", "rejected")}
            )
        if saved["court_target"]:
            values.update(
                court_role=(saved["court_role"],),
                court_target=(
                    str(
                        next(
                            i
                            for i, x in enumerate(data["people"])
                            if x["ref"] == saved["court_target"]
                        )
                    ),
                ),
            )

    async def save(current: discord.Interaction, selected: dict[str, Any]) -> str:
        names = tuple(data["starting"][int(i)] for i in selected["assets"])
        choice = Selection(
            frame=data["frame"],
            name=selected["name"],
            appearance=selected["appearance"],
            assets=tuple(
                AssetChoice(name=name, description=selected[key])
                for name, key in zip(
                    names, ("first_description", "second_description"), strict=True
                )
            ),
            retained_asset=selected["keep_asset"][0],
            retained_rule=selected["keep_rule"][0],
            retained_receipt=next(
                (
                    x["receipt"]
                    for x in data.get("class_sources", [])
                    if x["rule"] == selected["keep_rule"][0]
                ),
                None,
            ),
            account=selected["account"],
            fanbase=Fanbase(
                demographics=tuple(selected["demographics"]),
                demanded=tuple(selected["demanded"]),
                rejected=tuple(selected["rejected"]),
            )
            if data["frame"] == "THE PRINCE"
            else None,
            court_role=selected["court_role"][0] if data["frame"] == "THE RED QUEEN" else None,
            court_target=ActorRef.model_validate(
                data["people"][int(selected["court_target"][0])]["ref"]
            )
            if data["frame"] == "THE RED QUEEN"
            else None,
            psych_strings=tuple(ActorRef.model_validate(x) for x in data["strings"])
            if data["frame"] == "CHANGELING"
            else (),
        )
        await asyncio.to_thread(
            service.change,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            selection=choice,
        )
        return "Exact choices saved without charging. Reopen the request for consent and payment."

    form = NativeForm(
        viewer.user_id,
        "Configure " + data["frame"],
        "The two new starting Assets are additional to your one retained old Asset. "
        "Changing this plan clears any previous external Court consent.",
        fields,
        save,
        values=values,
    )
    await reply(interaction, form.text(), form)


async def open_plan(
    interaction: discord.Interaction, service: FrameSwapService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] == "resolved":
        await reply(
            interaction, "This exchange plan is closed. Its actual source history is retained."
        )
        return
    if not data["own"]:

        async def accept(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.change,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                accept=True,
            )
            return "Your exact AM assignment was accepted; no other player's consent was supplied."

        form = NativeForm(
            viewer.user_id,
            "Your proposed Court assignment",
            "The new Frame proposes assigning you " + data["assignment"]["role"] + ". "
            "This is an actual mechanical assignment. You may leave this request unanswered.",
            [Field("confirm", "Your own acceptance", (("yes", "Accept this exact assignment"),))],
            accept,
        )
        await reply(interaction, form.text(), form)
        return
    if data["selection"] is None:
        await configure(interaction, service, identity)
        return

    async def act(current: discord.Interaction, values: dict[str, Any]) -> str:
        action = values["operation"][0]
        await asyncio.to_thread(
            service.change,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            cancel=action == "cancel",
            purchase=action == "pay",
            expected=data["expected"],
            delivered=values["delivered"] == ("yes",),
            home_reinstalled=values.get("home_reinstalled") == ("yes",),
        )
        return (
            "Four Permissions paid; your actual new Frame is assigned."
            if action == "pay"
            else "Unpaid plan cancelled; no Permissions were spent."
        )

    form = NativeForm(
        viewer.user_id,
        "Review optional Frame Swap",
        "Destination: " + data["frame"] + ". Keep one real old Asset and rule, start the new "
        "Frame baseline, and pay four Permissions. Your Girl's resources and body remain hers.",
        [
            Field(
                "operation",
                "Your owned decision",
                (
                    ("pay", "Pay four and exchange"),
                    ("cancel", "Cancel unpaid plan"),
                ),
            ),
            Field(
                "delivered",
                "Actual new Frame delivered at your body's recorded location",
                (("yes", "Yes, actual delivery is complete"), ("no", "Delivery not confirmed")),
            ),
        ],
        act,
    )
    from girlframe.engine.m3_home import RULE as HOME_RULE

    if data["selection"]["retained_rule"] == HOME_RULE:
        form.fields.append(
            Field(
                "home_reinstalled",
                "Original Home possessions moved and new corner/vent prepared",
                (
                    ("yes", "Yes, original possessions moved and comforts prepared"),
                    ("no", "Home reinstallation not yet performed"),
                ),
            )
        )
    form.add_item(EditPlan(form, service, identity))
    await reply(interaction, form.text(), form)


class EditPlan(discord.ui.Button[NativeForm]):
    def __init__(self, form: NativeForm, service: FrameSwapService, identity: str):
        super().__init__(label="Edit saved plan", row=4)
        self.form, self.service, self.identity = form, service, identity

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.form.interaction_check(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await configure(interaction, self.service, self.identity)
