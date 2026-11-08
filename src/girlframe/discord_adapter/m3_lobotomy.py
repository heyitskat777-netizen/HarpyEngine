"""Private surgery selectors and original-patient narrative replies."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_lobotomy_state import OPTIONS, Plan
from girlframe.services.m3_lobotomy import LobotomyService
from girlframe.services.onboarding import WorkflowError

LABELS = {
    "memories": "Reset starting Identities, then erase two",
    "play": "Remove the ability to roll one Play",
    "name": "Remove or replace her name",
    "bonds": "Erase all Bonds; assign optional new Bonds",
    "memory": "Implant a memory and its new Identity",
}


class EffectsSelect(discord.ui.Select["EffectsView"]):
    def __init__(self, parent: "EffectsView"):
        self.parent_view = parent
        super().__init__(
            placeholder="Choose one to three actual surgery effects",
            min_values=1,
            max_values=3,
            options=[discord.SelectOption(label=LABELS[x], value=x) for x in OPTIONS],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await open_plan(
                interaction, self.parent_view.service, self.parent_view.identity, tuple(self.values)
            )
        except WorkflowError as error:
            await reply(interaction, str(error))


class EffectsView(discord.ui.View):
    def __init__(self, owner: int, service: LobotomyService, identity: str):
        super().__init__(timeout=600)
        self.owner, self.service, self.identity = owner, service, identity
        self.add_item(EffectsSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "These surgery choices belong to the actual inflictor.")
            return False
        return True


async def open_plan(
    interaction: discord.Interaction,
    service: LobotomyService,
    identity: str,
    options: tuple[str, ...],
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["phase"] != "plan" or not data["can_act"] or not set(options) <= set(OPTIONS):
        raise WorkflowError("Reopen the current inflictor's actual surgery menu.")
    fields = [
        Field("room", "Describe the surgery room", paragraph=True),
        Field("restraints", "Describe her actual restraints", paragraph=True),
        Field("tools", "Describe your tools", paragraph=True),
    ]
    if "memories" in options:
        fields.append(
            Field(
                "erase",
                "Erase two starting Identity slots",
                tuple(
                    (str(i), label)
                    for i, label in enumerate(data["starting"])
                    if i not in data["protected_slots"]
                ),
                2,
                2,
            )
        )
    if "play" in options:
        fields.append(
            Field(
                "play",
                "Remove ability to roll this Play",
                tuple((x, x.replace("_", " ").title()) for x in data["plays"]),
            )
        )
    if "name" in options:
        fields.append(Field("name", "Optional new name; blank removes it", required=False))
    if "bonds" in options:
        depths = (("0", "No Bond"), ("1", "Personal"), ("2", "Intense"))
        fields.extend(
            [
                Field("inflictor_depth", "New Bond with you", depths),
                Field(
                    "other",
                    "Optional other character",
                    (("none", "No other new Bond"),)
                    + tuple((row["token"], row["label"]) for row in data["actors"]),
                ),
                Field("other_depth", "Other character's Bond", depths),
            ]
        )
    if "memory" in options:
        fields.extend(
            [
                Field("memory", "Describe the implanted memory", paragraph=True),
                Field("identity", "New Identity based on that memory"),
            ]
        )
        ordinary = sum(not x["protected"] or x.get("paired", False) for x in data["identities"])
        if "memories" not in options and ordinary >= 4:
            fields.append(
                Field(
                    "replace",
                    "Replace an unprotected Identity",
                    tuple((x["id"], x["name"]) for x in data["identities"] if not x["protected"]),
                )
            )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        other = next(
            (row for row in data["actors"] if row["token"] == values.get("other", ("none",))[0]),
            None,
        )
        if values.get("other", ("none",))[0] != "none" and other is None:
            raise WorkflowError(
                "Choose an actual other character from this surgery's current menu."
            )
        selected = Plan.model_validate(
            dict(
                options=options,
                room=values["room"],
                restraints=values["restraints"],
                tools=values["tools"],
                erase_slots=tuple(int(x) for x in values.get("erase", ())),
                forbidden_play=values.get("play", (None,))[0],
                new_name=values.get("name", ""),
                inflictor_depth=int(values.get("inflictor_depth", ("0",))[0]),
                other=ActorRef.model_validate(other["ref"]) if other else None,
                other_depth=int(values.get("other_depth", ("0",))[0]),
                memory=values.get("memory", ""),
                identity=values.get("identity", ""),
                replace_identity=values.get("replace", (None,))[0],
            )
        )
        await asyncio.to_thread(
            service.prepare,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["game_revision"],
            selected,
        )
        return "Surgery prepared. The original patient must describe the printed responses."

    form = NativeForm(
        viewer.user_id,
        "Experimental surgery — " + clean(data["patient"]),
        "Choose actual effects. The patient supplies her own descriptions.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_lobotomy(
    interaction: discord.Interaction, service: LobotomyService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if not data["can_act"]:
        await reply(interaction, "Surgery: " + data["phase"] + ". Waiting for its actual owner.")
        return
    if data["phase"] == "plan":
        await reply(
            interaction,
            "Choose one to three surgery effects. The Punishment stays pending.",
            EffectsView(viewer.user_id, service, identity),
        )
        return
    if data["phase"] == "responses":
        fields = [Field(key, prompt, paragraph=True) for key, prompt in data["prompts"].items()]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["game_revision"],
                values,
            )
            return (
                "Your descriptions are saved. "
                "The actual inflictor must finish the prepared surgery."
            )

        plan = data["plan"]
        instructions = "\n".join(clean(plan[x]) for x in ("room", "restraints", "tools"))
    else:
        fields = [
            Field("confirm", "Complete the actual prepared surgery", (("yes", "Finish surgery"),))
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.finish, viewer_from_interaction(current), str(current.id), identity
            )
            return "Actual surgery applied and its original Punishment recorded."

        instructions = (
            "The original patient supplied her own descriptions. Apply only the saved effects."
        )
    form = NativeForm(
        viewer.user_id,
        "Experimental surgery — " + clean(data["patient"]),
        instructions,
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
