"""Native paid-scene selectors and separately owned agreements, entry and closure."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_scene_requisitions import Kind
from girlframe.services.m3_scene_requisitions import SceneRequisitionService
from girlframe.services.onboarding import WorkflowError

LABELS = {"privacy": "Privacy", "visiting_home": "Visiting Home"}


async def open_purchase(
    interaction: discord.Interaction,
    service: SceneRequisitionService,
    kind: Kind,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.scene_purchase_view, viewer)
    choices = {ActorRef.model_validate(x["ref"]).token: x for x in data["companions"]}
    fields = []
    if kind == "privacy":
        if not choices:
            raise WorkflowError("Privacy needs another actual current Girl.")
        fields.append(
            Field(
                "companion",
                "The other Girl",
                tuple((key, value["label"]) for key, value in choices.items()),
            )
        )
    fields.extend(
        [
            Field("account", "Describe your actual paid request", paragraph=True),
            Field(
                "payment",
                "Explicit payment",
                (("yes", "Pay " + ("1 Permission" if kind == "privacy" else "2 Permissions")),),
            ),
        ]
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        companion = (
            ActorRef.model_validate(choices[values["companion"][0]]["ref"])
            if kind == "privacy"
            else None
        )
        result = await asyncio.to_thread(
            service.buy_scene,
            viewer_from_interaction(current),
            str(current.id),
            ActorRef.model_validate(data["actor"]),
            data["source_sha256"],
            kind,
            values["account"],
            companion,
        )
        return (
            "Paid request saved: "
            + str(result["id"])
            + ". Reopen requests after its actual qualifier."
        )

    form = NativeForm(
        viewer.user_id,
        "Purchase " + LABELS[kind],
        "Your original Girl pays once. Privacy applies during the next actual Off-Duty period; "
        "Visiting Home waits for your next actual ordinary eight-plus roll. "
        "No scene occurs at purchase.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


class DetailPages(discord.ui.View):
    def __init__(self, service: SceneRequisitionService, owner: int, identity: str):
        super().__init__(timeout=600)
        self.service, self.owner, self.identity, self.page = service, owner, identity, 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "These details belong to another actual participant.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        data = await asyncio.to_thread(
            self.service.scene_get, viewer_from_interaction(interaction), self.identity
        )
        saved = data["benefit"]
        scene = saved["scene"]
        text = LABELS[data["kind"]] + "\n"
        if scene:
            text += "Actual scene: " + clean(scene["account"])
            if scene["home"]:
                text += "\nPre-Piloting life: " + clean(scene["home"])
            if scene["closed_by"] is not None or scene["career_end"] is not None:
                text += "\nClose: " + clean(scene["close_account"])
        else:
            text += "Your original benefit is waiting for an owned scene."
        pages = [text[index : index + 1650] for index in range(0, len(text), 1650)]
        self.page = min(max(0, self.page), len(pages) - 1)
        self.previous.disabled, self.next.disabled = self.page == 0, self.page + 1 == len(pages)
        await reply(interaction, pages[self.page] + f"\nPage {self.page + 1}/{len(pages)}", self)

    @discord.ui.button(label="Previous", row=0)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        self.page -= 1
        await self.show(interaction)

    @discord.ui.button(label="Next", row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await interaction.response.defer(ephemeral=True)
        self.page += 1
        await self.show(interaction)

    @discord.ui.button(label="Return to decisions", row=0)
    async def decisions(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await open_scene(interaction, self.service, self.identity)


class DetailsButton(discord.ui.Button[NativeForm]):
    def __init__(self, service: SceneRequisitionService, owner: int, identity: str):
        super().__init__(label="Read all saved details", row=3)
        self.service, self.owner, self.identity = service, owner, identity

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner:
            await reply(interaction, "This form belongs to another participant.")
            return
        await interaction.response.defer(ephemeral=True)
        await DetailPages(self.service, self.owner, self.identity).show(interaction)


async def open_scene(
    interaction: discord.Interaction,
    service: SceneRequisitionService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.scene_get, viewer, identity, interaction.channel_id)
    saved, own = data["benefit"], data["own"]
    scene = saved["scene"]
    if data.get("deferred"):
        await reply(
            interaction,
            "This paid scene has not been used or declined. "
            + (
                "Its original entitlement moved to a new period; reopen your inbox."
                if data.get("transfer_work")
                else "It stays suspended until the original condition and restoration are complete."
            ),
        )
        return
    if data["state"] == "resolved":
        await DetailPages(service, viewer.user_id, identity).show(interaction)
        return
    choices = []
    fields = []
    if scene is None and own:
        choices = [("propose", "Set the actual scene"), ("decline", "Decline without a refund")]
        if data["kind"] == "visiting_home":
            fields += [
                Field(
                    "supervisor",
                    "Actual supervising role",
                    tuple(
                        (x["token"], x["label"])
                        for x in data["roles"]
                        if x["ref"] != saved["actor"] and x["can_supervise"]
                    ),
                    minimum=0,
                    required=False,
                ),
                Field("home", "Your pre-Piloting life", paragraph=True, required=False),
            ]
        fields.append(Field("account", "Describe the scene or your decline", paragraph=True))
    elif scene is not None:
        if own and scene["entered_event"] is None:
            choices.append(("reset", "Revise the unentered scene; clear its agreements"))
        if data["can_attest"]:
            choices.append(("attest", "Confirm my own participation or supervision"))
        if (
            own
            and scene["entered_event"] is None
            and set(scene["present"]) == {x["controller"] for x in scene["roles"]}
        ):
            choices.append(("enter", "Enter the agreed actual scene"))
        if data["kind"] == "privacy" or (own and data["active"]):
            choices.append(("close", "End my actual scene participation"))
            fields.append(
                Field("account", "Brief actual close account", paragraph=True, required=False)
            )
    if not choices:
        await DetailPages(service, viewer.user_id, identity).show(interaction)
        return
    fields.insert(0, Field("operation", "Your owned decision", tuple(choices)))
    role_by_token = {x["token"]: x for x in data["roles"]}

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        actor = viewer_from_interaction(current)
        operation = values["operation"][0]
        args = (actor, str(current.id), identity, data["revision"])
        if operation == "propose":
            if current.channel_id is None or data["cast_revision"] is None:
                raise WorkflowError("Use the actual joined scene channel to set its scene.")
            supervisor = values.get("supervisor", ())
            await asyncio.to_thread(
                service.propose_scene,
                *args,
                current.channel_id,
                data["cast_revision"],
                values["account"],
                supervisor=ActorRef.model_validate(role_by_token[supervisor[0]]["ref"])
                if supervisor
                else None,
                home=values.get("home", ""),
            )
        elif operation == "attest":
            await asyncio.to_thread(service.attest_scene, *args)
        elif operation == "enter":
            await asyncio.to_thread(service.enter_scene, *args)
        elif operation == "reset":
            await asyncio.to_thread(service.reset_scene, *args)
        elif operation == "decline":
            await asyncio.to_thread(service.decline_scene, *args, values["account"])
        else:
            await asyncio.to_thread(service.close_scene, *args, values.get("account", ""))
        return "Your owned decision is saved. Reopen requests for the actual current scene."

    form = NativeForm(
        viewer.user_id,
        LABELS[data["kind"]] + " — your scene",
        "Review the saved details before agreeing. Each human supplies their own participation. "
        "The purchaser enters only after agreement. Safety pause remains available.",
        fields,
        submit,
    )
    form.add_item(DetailsButton(service, viewer.user_id, identity))
    await reply(interaction, form.text(), form)
