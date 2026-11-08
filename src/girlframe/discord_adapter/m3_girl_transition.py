"""Private native controls for actual post-Defeat Girl baseline setup."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.creation_details import DESIRES, MAXIMS, DesireChoice
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_transition_state import Investor, Plan
from girlframe.services.m3_girl_transition import GirlTransitionService


def choices(data: dict[str, Any]) -> tuple[dict[str, ActorRef], tuple[tuple[str, str], ...]]:
    refs = {
        ActorRef.model_validate_json(json.dumps(x["ref"])).token: ActorRef.model_validate_json(
            json.dumps(x["ref"])
        )
        for x in data["people"]
    }
    labels = tuple(
        (ActorRef.model_validate_json(json.dumps(x["ref"])).token, x["label"])
        for x in data["people"]
    )
    return refs, labels


async def open_transition(
    interaction: discord.Interaction, service: GirlTransitionService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    text = "**Girl playbook change**\n" + clean(data["old_book"]) + " → " + clean(data["book"])
    if data["complete"]:
        await reply(interaction, text + "\nThe original Girl's actual setup is complete.")
        return
    if data["can_respond"]:
        if data["role"] == "mentor":
            fields = [
                Field(
                    "callsign", "Choose your trainee's callsign (1–80 characters)", paragraph=True
                )
            ]
        elif data["role"] == "pair":
            text += (
                "\nAccepting installs your Intense Bond and the owner's selected "
                "protected Paired Identity."
            )
            fields = [
                Field(
                    "decision",
                    "Your Pair response",
                    (("yes", "Accept this Pair relationship"), ("no", "Decline")),
                )
            ]
        else:
            fields = [
                Field(
                    "desires",
                    "Choose your own investor desires",
                    tuple((str(i), x) for i, x in enumerate(DESIRES)),
                    1,
                    2,
                )
            ]

        async def respond(current: discord.Interaction, values: dict[str, Any]) -> str:
            kwargs: dict[str, Any] = {}
            if data["role"] == "mentor":
                kwargs["callsign"] = values["callsign"]
            elif data["role"] == "pair":
                kwargs["accepted"] = values["decision"][0] == "yes"
            else:
                kwargs["desires"] = DesireChoice(slots=tuple(int(x) for x in values["desires"]))
            await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                **kwargs,
            )
            return "Your actual choice is saved. The original Girl confirms the complete setup."

        form = NativeForm(interaction.user.id, "Your actual setup response", text, fields, respond)
        await reply(interaction, form.text(), form)
        return
    if data["can_assign"]:
        refs, options = choices(data)
        if not options:
            await reply(interaction, text + "\nAn actual current other Girl is required as Mentor.")
            return

        async def assign(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.assign,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                refs[values["mentor"][0]],
            )
            return "The actual Mentor is assigned. They choose the callsign privately."

        form = NativeForm(
            interaction.user.id,
            "Assign the actual Mentor",
            text,
            [Field("mentor", "Choose the current Girl Mentor", options)],
            assign,
        )
        await reply(interaction, form.text(), form)
        return
    if data["owner"]:
        await reply(
            interaction,
            text + "\nRetained resources stay as they are. Complete actual new rule choices below.",
            TransitionMenu(interaction.user.id, service, identity, data),
        )
        return
    await reply(
        interaction,
        text
        + (
            "\nOriginal context requires recovery."
            if data["stale"]
            else "\nWaiting for an original chooser."
        ),
    )


class TransitionMenu(discord.ui.View):
    def __init__(
        self, owner: int, service: GirlTransitionService, identity: str, data: dict[str, Any]
    ):
        super().__init__(timeout=600)
        self.owner, self.service, self.identity, self.data = owner, service, identity, data
        self.configure_button.disabled = not data["can_configure"]
        self.finish.disabled = not data["can_finalize"]
        self.standards.disabled = not data["needs_standards"]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await reply(interaction, "This original Girl setup belongs to its actual owner.")
        return False

    @discord.ui.button(label="Configure / revise", style=discord.ButtonStyle.primary)
    async def configure_button(
        self, interaction: discord.Interaction, button: discord.ui.Button["TransitionMenu"]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await asyncio.to_thread(
            self.service.get, viewer_from_interaction(interaction), self.identity
        )
        await open_configuration(interaction, self.service, data)

    @discord.ui.button(label="Choose standards", style=discord.ButtonStyle.secondary)
    async def standards(
        self, interaction: discord.Interaction, button: discord.ui.Button["TransitionMenu"]
    ) -> None:
        from girlframe.discord_adapter.m3_standards import open_standards
        from girlframe.services.m3_standards import StandardsService

        await interaction.response.defer(ephemeral=True)
        await open_standards(interaction, StandardsService(self.service.store))

    @discord.ui.button(label="Confirm complete setup", style=discord.ButtonStyle.success)
    async def finish(
        self, interaction: discord.Interaction, button: discord.ui.Button["TransitionMenu"]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await asyncio.to_thread(
            self.service.get, viewer_from_interaction(interaction), self.identity
        )

        view = TransitionReview(interaction.user.id, self.service, self.identity, data)
        await reply(interaction, view.text(), view)

    @discord.ui.button(label="Review saved choices", style=discord.ButtonStyle.secondary)
    async def review(
        self, interaction: discord.Interaction, button: discord.ui.Button["TransitionMenu"]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await asyncio.to_thread(
            self.service.get, viewer_from_interaction(interaction), self.identity
        )
        view = TransitionReview(interaction.user.id, self.service, self.identity, data)
        await reply(interaction, view.text(), view)


class TransitionReview(discord.ui.View):
    def __init__(
        self, owner: int, service: GirlTransitionService, identity: str, data: dict[str, Any]
    ):
        super().__init__(timeout=600)
        self.owner, self.service, self.identity, self.data = owner, service, identity, data
        plan = data.get("plan") or {}
        lines = ["Actual new book: " + data["book"], "Change: " + plan.get("account", "Unchosen")]
        labels = {x["ref"]["entity"]: x["label"] for x in data["people"]}
        if plan.get("pair"):
            lines += [
                "Pair: " + labels.get(plan["pair"]["entity"], "Original Girl unavailable"),
                "Paired Identity: " + str(plan["paired_identity"]),
            ]
        if plan.get("maxims"):
            lines += ["Maxim: " + MAXIMS[x] for x in plan["maxims"]]
        if plan.get("dna_basis"):
            lines.append("DNA basis: " + plan["dna_basis"])
        for investor in plan.get("investors", ()):
            lines.append(
                "NPC "
                + investor["npc"]
                + ": "
                + ", ".join(DESIRES[x] for x in investor["desires"]["slots"])
            )
        for kind, response in data.get("responses", {}).items():
            if kind == "assignment":
                lines.append(
                    "Mentor: "
                    + labels.get(response["mentor"]["entity"], "Original Girl unavailable")
                )
            elif kind == "mentor":
                lines.append("Mentor's callsign: " + response["callsign"])
            elif kind == "pair":
                lines.append(
                    "Pair response: " + ("Accepted" if response["accepted"] else "Declined")
                )
            elif kind == "investor":
                lines.append(
                    "Handler's desires: "
                    + ", ".join(DESIRES[x] for x in response["desires"]["slots"])
                )
        value = clean("\n".join(lines))
        self.pages = tuple(value[i : i + 1600] for i in range(0, len(value), 1600)) or (
            "No saved choices.",
        )
        self.index = 0
        self.controls()

    def controls(self) -> None:
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.apply.disabled = self.index != len(self.pages) - 1 or not self.data["can_finalize"]

    def text(self) -> str:
        return (
            f"**Actual setup review {self.index + 1}/{len(self.pages)}**\n" + self.pages[self.index]
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await reply(interaction, "These saved choices belong to their actual owner.")
        return False

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button["TransitionReview"]
    ) -> None:
        self.index = max(0, self.index - 1)
        self.controls()
        await interaction.response.defer()
        await reply(interaction, self.text(), self)

    @discord.ui.button(label="Next")
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button["TransitionReview"]
    ) -> None:
        self.index = min(len(self.pages) - 1, self.index + 1)
        self.controls()
        await interaction.response.defer()
        await reply(interaction, self.text(), self)

    @discord.ui.button(label="Apply exactly these choices", style=discord.ButtonStyle.success)
    async def apply(
        self, interaction: discord.Interaction, button: discord.ui.Button["TransitionReview"]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await asyncio.to_thread(
            self.service.finalize,
            viewer_from_interaction(interaction),
            str(interaction.id),
            self.identity,
            self.data["revision"],
            self.data["game_revision"],
        )
        await reply(interaction, "Your actual new Girl baseline setup is complete.")


async def open_configuration(
    interaction: discord.Interaction, service: GirlTransitionService, data: dict[str, Any]
) -> None:
    book = data["book"]
    fields = [Field("account", "Describe the actual Girl change", paragraph=True)]
    refs, options = choices(data)
    if book == "BONDED":
        if not options or not data["identities"]:
            await reply(
                interaction, "An actual other Girl and owned ordinary/Paired Identity are required."
            )
            return
        fields += [
            Field("pair", "Choose your actual Pair", options),
            Field(
                "identity",
                "Choose your own Paired Identity slot",
                tuple((x["id"], x["name"]) for x in data["identities"]),
            ),
        ]
    if book == "OLDGEN":
        fields.append(
            Field(
                "maxims",
                "Choose exactly two maxims",
                tuple((str(i), x) for i, x in enumerate(MAXIMS)),
                2,
                2,
            )
        )
    if book == "VATGROWN":
        if not data["investors"]:
            await reply(interaction, "Link your retained starting NPC Bonds to actual NPCs first.")
            return
        fields.append(Field("dna", "Name the basis for your DNA", paragraph=True))
        for i, investor in enumerate(data["investors"]):
            fields.append(
                Field(
                    "investor_" + str(i),
                    "Desires: " + investor["name"],
                    tuple((str(n), x) for n, x in enumerate(DESIRES)),
                    1,
                    2,
                )
            )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        plan = Plan(
            account=values["account"],
            pair=refs[values["pair"][0]] if book == "BONDED" else None,
            paired_identity=values["identity"][0] if book == "BONDED" else None,
            maxims=tuple(int(x) for x in values.get("maxims", ())),
            dna_basis=values.get("dna", ""),
            investors=tuple(
                Investor(
                    npc=x["id"],
                    desires=DesireChoice(slots=tuple(int(n) for n in values["investor_" + str(i)])),
                )
                for i, x in enumerate(data["investors"])
            )
            if book == "VATGROWN"
            else (),
        )
        await asyncio.to_thread(
            service.configure,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            plan,
        )
        return (
            "Your actual setup is saved. Reopen to review original responses "
            "and confirm completion."
        )

    form = NativeForm(
        interaction.user.id,
        "Configure your new Girl baseline",
        "Keep existing Identities, Assets, Bonds, marks and resources. "
        "New starting grants are not applied. "
        "Only new continuous rule choices are configured here.",
        fields,
        submit,
    )
    if data["plan"]:
        form.values["account"] = data["plan"]["account"]
        saved = data["plan"]
        if saved.get("pair"):
            form.values["pair"] = (ActorRef.model_validate_json(json.dumps(saved["pair"])).token,)
            form.values["identity"] = (saved["paired_identity"],)
        if saved.get("maxims"):
            form.values["maxims"] = tuple(str(x) for x in saved["maxims"])
        if saved.get("dna_basis"):
            form.values["dna"] = saved["dna_basis"]
        for i, investor in enumerate(data["investors"]):
            selected = next((x for x in saved["investors"] if x["npc"] == investor["id"]), None)
            if selected:
                form.values["investor_" + str(i)] = tuple(
                    str(x) for x in selected["desires"]["slots"]
                )
    await reply(interaction, form.text(), form)
