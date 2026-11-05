"""Private resumable Handler creation and explicit original-player agreements."""

import asyncio
import json
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_state import (
    GEAR,
    HISTORY_LABELS,
    PLAYBOOKS,
    Draft,
    GearDetail,
    NpcStarting,
    StartingBond,
)
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import WorkflowError


class HandlerMenu(discord.ui.View):
    def __init__(self, service: HandlerCreationService, owner: int, data: dict[str, Any]):
        super().__init__(timeout=600)
        self.service, self.owner, self.data = service, owner, data
        self.details.disabled = self.relationships.disabled = not data["editable"]
        self.npc_relationship.disabled = (
            not data["editable"] or data["draft"]["playbook"] != "Insurgent"
        )
        self.propose.disabled = self.activate.disabled = not data["editable"] or bool(
            data["missing"]
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This creation menu belongs to its original Handler.")
            return False
        return True

    @discord.ui.button(label="Edit details", row=0)
    async def details(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await open_details(interaction, self.service)

    @discord.ui.button(label="Starting relationships", row=0)
    async def relationships(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await open_starting(interaction, self.service)

    @discord.ui.button(label="NPC relationship history", row=2)
    async def npc_relationship(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await open_npc_relationship(interaction, self.service)

    @discord.ui.button(label="Send shared requests", row=1)
    async def propose(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            result = await asyncio.to_thread(
                self.service.propose,
                viewer_from_interaction(interaction),
                str(interaction.id),
                self.data["revision"],
                generation=self.data["generation"],
            )
            await reply(
                interaction,
                "Starting relationship requests saved. "
                "Each original participant owns their response. "
                + "Request count: "
                + str(len(result["ids"])),
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @discord.ui.button(label="Review activation", row=1)
    async def activate(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await open_activation(interaction, self.service)

    @discord.ui.button(label="Read saved sheet", row=2)
    async def history(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await HandlerHistory(self.service, self.owner).show(interaction)


class HandlerHistory(discord.ui.View):
    def __init__(self, service: HandlerCreationService, owner: int):
        super().__init__(timeout=600)
        self.service, self.owner, self.index = service, owner, 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This private sheet belongs to another participant.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        data = await asyncio.to_thread(self.service.view, viewer_from_interaction(interaction))
        draft = Draft.model_validate_json(json.dumps(data["draft"]))
        raw_pages = [
            "Playbook: " + str(draft.playbook or "Unchosen") + "\nName: " + draft.name,
            "Appearance\n" + draft.appearance,
            "Outfit\n" + draft.outfit,
            "Background\n" + draft.background,
            *(dict(GEAR)[x.kind] + "\n" + x.description for x in draft.gear),
            *(
                "Starting relationship "
                + str(i + 1)
                + "\n"
                + x.history
                + "\n"
                + x.rank.title()
                + "; "
                + ("Intense" if x.depth == 2 else "Personal")
                for i, x in enumerate(draft.starting)
            ),
        ]
        pages = [
            clean(page)[i : i + 1500]
            for page in raw_pages
            for i in range(0, max(1, len(clean(page))), 1500)
        ]
        self.index = min(max(self.index, 0), len(pages) - 1)
        self.previous.disabled, self.next.disabled = self.index == 0, self.index == len(pages) - 1
        await reply(
            interaction,
            "**Your saved Handler sheet**\n"
            + pages[self.index]
            + f"\nPage {self.index + 1}/{len(pages)}. "
            + ("Activated." if data["activated"] else "Creation progress only."),
            self,
        )

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.index -= 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)

    @discord.ui.button(label="Next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.index += 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)


async def open_handler(interaction: discord.Interaction, service: HandlerCreationService) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))
    text = "**Your Handler creation**\n" + (
        "Activated."
        if data["activated"]
        else "Missing: " + ", ".join(data["missing"])
        if data["missing"]
        else "Complete draft. Send shared requests, then review activation."
    )
    await reply(interaction, text, HandlerMenu(service, interaction.user.id, data))


async def open_details(interaction: discord.Interaction, service: HandlerCreationService) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))
    if not data["editable"]:
        raise WorkflowError("Reopen the original unactivated Handler appointment before edits.")
    draft = Draft.model_validate_json(json.dumps(data["draft"]))
    values: dict[str, Any] = {
        k: getattr(draft, k) for k in ("name", "appearance", "outfit", "background")
    }
    values["playbook"] = (draft.playbook,) if draft.playbook else ()
    fields = [
        Field(
            "playbook",
            "Handler playbook",
            tuple((x, x) for x in PLAYBOOKS),
            minimum=0,
            required=False,
        ),
        *(
            Field(k, k.title(), paragraph=k != "name", required=False)
            for k in ("name", "appearance", "outfit", "background")
        ),
    ]
    for i in range(2):
        fields.extend(
            [
                Field(
                    "gear_" + str(i), "Gear choice " + str(i + 1), GEAR, minimum=0, required=False
                ),
                Field(
                    "description_" + str(i),
                    "Describe gear choice " + str(i + 1),
                    paragraph=True,
                    required=False,
                ),
            ]
        )
        if i < len(draft.gear):
            values["gear_" + str(i)] = (draft.gear[i].kind,)
            values["description_" + str(i)] = draft.gear[i].description

    async def submit(current: discord.Interaction, answers: dict[str, Any]) -> str:
        playbook = answers.get("playbook", (None,))[0] if answers.get("playbook") else None
        updated = draft.model_copy(
            update={
                "playbook": playbook,
                **{k: answers.get(k, "") for k in ("name", "appearance", "outfit", "background")},
                "gear": tuple(
                    GearDetail(
                        kind=answers["gear_" + str(i)][0],
                        description=answers.get("description_" + str(i), ""),
                    )
                    for i in range(2)
                    if answers.get("gear_" + str(i))
                ),
                **(
                    {"starting": (), "surveilled": (), "sympathizer": None, "npc_starting": ()}
                    if playbook != draft.playbook
                    else {}
                ),
            }
        )
        await asyncio.to_thread(
            service.save,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            data["appointment"],
            updated,
            generation=data["generation"],
        )
        return "Private progress saved. Reopen Handler creation to choose starting relationships."

    form = NativeForm(
        interaction.user.id,
        "Handler details",
        "Save incomplete progress at any time. "
        "Changing playbook requires fresh starting relationship choices.",
        fields,
        submit,
        values=values,
    )
    await reply(interaction, form.text(), form)


async def open_starting(interaction: discord.Interaction, service: HandlerCreationService) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))
    draft = Draft.model_validate_json(json.dumps(data["draft"]))
    if not data["editable"] or draft.playbook is None:
        raise WorkflowError("Choose a playbook in your current unactivated Handler draft first.")
    playbook = draft.playbook
    count = 1 if draft.playbook == "Scientist" else 2
    roster = {x["token"]: ActorRef.model_validate(x["ref"]) for x in data["pilots"]}
    if len(roster) < count:
        raise WorkflowError("The printed starting selection needs more actual current Girls.")
    fields, values = [], {}
    for i in range(count):
        prefix = str(i) + "_"
        fields.extend(
            [
                Field(
                    prefix + "pilot",
                    "Choose your starting Girl"
                    if draft.playbook == "Scientist"
                    else "Choose your Ace"
                    if i == 0
                    else "Choose your Dog",
                    tuple((x["token"], x["label"]) for x in data["pilots"]),
                ),
                Field(
                    prefix + "prompt",
                    "Relationship prompt or custom history",
                    (("custom", "Custom shared history"),)
                    + tuple(
                        (str(j), name) for j, name in enumerate(HISTORY_LABELS[draft.playbook])
                    ),
                ),
                Field(prefix + "history", "Shared history details", paragraph=True, required=False),
            ]
        )
        if draft.playbook == "Mistress":
            fields.append(
                Field(
                    prefix + "depth", "Starting Bond depth", (("1", "Personal"), ("2", "Intense"))
                )
            )
        if draft.playbook == "Scientist":
            fields.append(
                Field(prefix + "rank", "Starting Status", (("ace", "Ace"), ("dog", "Dog")))
            )
        if i < len(draft.starting):
            previous = draft.starting[i]
            values.update(
                {
                    prefix + "pilot": (previous.pilot.token,),
                    prefix + "history": previous.history,
                    prefix + "prompt": (
                        str(previous.prompt) if previous.prompt is not None else "custom",
                    ),
                    prefix + "depth": (str(previous.depth),),
                    prefix + "rank": (previous.rank,),
                }
            )
    if draft.playbook == "Insurgent":
        choices = tuple((x["id"], x["name"]) for x in data["npcs"])
        if not choices:
            raise WorkflowError(
                "Introduce actual living NPCs before the Insurgent's starting selection."
            )
        fields.extend(
            [
                Field("surveilled", "Choose one or two Surveilled NPC Bonds", choices, 1, 2),
                Field("sympathizer", "Choose a Sympathizer NPC Bond", choices),
            ]
        )
        values.update(
            surveilled=draft.surveilled,
            sympathizer=(draft.sympathizer,) if draft.sympathizer else (),
        )

    async def submit(current: discord.Interaction, answers: dict[str, Any]) -> str:
        starting = []
        for i in range(count):
            prefix = str(i) + "_"
            prompt = answers[prefix + "prompt"][0]
            history = answers.get(prefix + "history", "").strip()
            if not history and prompt != "custom":
                history = HISTORY_LABELS[playbook][int(prompt)]
            starting.append(
                StartingBond(
                    pilot=roster[answers[prefix + "pilot"][0]],
                    history=history,
                    rank=answers[prefix + "rank"][0]
                    if draft.playbook == "Scientist"
                    else "ace"
                    if i == 0
                    else "dog",
                    depth=cast(Literal[1, 2], int(answers[prefix + "depth"][0]))
                    if draft.playbook == "Mistress"
                    else 1,
                    prompt=None if prompt == "custom" else int(prompt),
                )
            )
        updated = draft.model_copy(
            update={
                "starting": tuple(starting),
                "surveilled": tuple(answers.get("surveilled", ())),
                "sympathizer": answers["sympathizer"][0] if answers.get("sympathizer") else None,
                "npc_starting": tuple(
                    x
                    for x in draft.npc_starting
                    if x.npc.entity
                    in set(answers.get("surveilled", ())) | set(answers.get("sympathizer", ()))
                ),
            }
        )
        await asyncio.to_thread(
            service.save,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            data["appointment"],
            updated,
            generation=data["generation"],
        )
        return "Starting choices saved. Send shared requests from Handler creation."

    form = NativeForm(
        interaction.user.id,
        "Handler starting relationships",
        "Each chosen Girl owns her shared-history response. Trainer prompt selections "
        "also install their printed phrases when activation completes.",
        fields,
        submit,
        values=values,
    )
    await reply(interaction, form.text(), form)


async def open_npc_relationship(
    interaction: discord.Interaction, service: HandlerCreationService
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))
    draft = Draft.model_validate_json(json.dumps(data["draft"]))
    if not data["editable"] or draft.playbook != "Insurgent":
        raise WorkflowError("Reopen the actual Insurgent's unactivated creation.")
    wanted = set(draft.surveilled) | ({draft.sympathizer} if draft.sympathizer else set())
    choices = {x["id"]: x for x in data["npcs"] if x["id"] in wanted}
    if not choices:
        raise WorkflowError("Save the actual Surveilled and Sympathizer selections first.")

    async def submit(current: discord.Interaction, answers: dict[str, Any]) -> str:
        identity = answers["npc"][0]
        choice = choices[identity]
        package = NpcStarting(
            npc=ActorRef(kind="npc", entity=identity),
            controller=choice["controller"],
            history=answers["history"],
        )
        updated = draft.model_copy(
            update={
                "npc_starting": tuple(x for x in draft.npc_starting if x.npc.entity != identity)
                + (package,)
            }
        )
        await asyncio.to_thread(
            service.save,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            data["appointment"],
            updated,
            generation=data["generation"],
        )
        return "Private relationship history saved. Send shared requests for explicit NPC consent."

    form = NativeForm(
        interaction.user.id,
        "Starting NPC relationship",
        "Describe one selected NPC relationship. Its actual controller must explicitly accept "
        "the proposed Personal Bond, including when you control that NPC yourself.",
        [
            Field("npc", "Actual selected NPC", tuple((k, x["name"]) for k, x in choices.items())),
            Field("history", "Shared relationship history", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_npc_agreement(
    interaction: discord.Interaction, service: HandlerCreationService, identity: str
) -> None:
    await open_agreement(interaction, service, identity)


def agreement_text(data: dict[str, Any]) -> str:
    proposal = data["proposal"]
    if "relationship" in proposal:
        return str(
            "**Proposed new Handler–NPC relationship**\nHandler: "
            + clean(proposal["name"])
            + "\nNPC: "
            + clean(proposal["relationship"]["npc"]["entity"])
            + "\n"
            + clean(proposal["relationship"]["history"])
            + "\nStarting Bond: Personal. This exact history belongs to this new persona only."
        )
    bond = proposal["bond"]
    text = (
        "**Shared starting relationship**\nHandler: "
        + clean(proposal["name"])
        + "\n"
        + clean(bond["history"])
        + "\nStarting Status: "
        + bond["rank"].title()
        + "; Bond: "
        + ("Intense" if bond["depth"] == 2 else "Personal")
    )
    if proposal["phrases"]:
        text += "\nStarting conditioning: " + clean(", ".join(proposal["phrases"]))
    return str(text)


class AgreementPages(discord.ui.View):
    def __init__(self, service: HandlerCreationService, identity: str, owner: int):
        super().__init__(timeout=600)
        self.service, self.identity, self.owner, self.index = service, identity, owner, 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This shared request viewer belongs to another participant.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        data = await asyncio.to_thread(
            self.service.get_agreement, viewer_from_interaction(interaction), self.identity
        )
        text = agreement_text(data)
        pages = [text[i : i + 1500] for i in range(0, len(text), 1500)]
        self.index = min(max(0, self.index), len(pages) - 1)
        self.previous.disabled, self.next.disabled = self.index == 0, self.index == len(pages) - 1
        self.respond.disabled = self.index != len(pages) - 1 or not data["can_answer"]
        await reply(interaction, pages[self.index] + f"\nPage {self.index + 1}/{len(pages)}.", self)

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.index -= 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)

    @discord.ui.button(label="Next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.index += 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)

    @discord.ui.button(label="Choose your response")
    async def respond(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await open_agreement(interaction, self.service, self.identity, reviewed=True)


async def open_agreement(
    interaction: discord.Interaction,
    service: HandlerCreationService,
    identity: str,
    *,
    reviewed: bool = False,
) -> None:
    data = await asyncio.to_thread(
        service.get_agreement, viewer_from_interaction(interaction), identity
    )
    text = agreement_text(data)
    if len(text) > 1300 and not reviewed:
        await AgreementPages(service, identity, interaction.user.id).show(interaction)
        return
    if not data["can_answer"]:
        await reply(
            interaction,
            (text if len(text) <= 1300 else "Original shared request")
            + "\n"
            + str(data["decision"])
            + ("; original proposal is no longer current." if data["stale"] else "."),
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.answer,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["decision"][0] == "accept",
        )
        return "Your response is recorded: " + ("accepted." if result["accepted"] else "declined.")

    form = NativeForm(
        interaction.user.id,
        "Your starting relationship",
        text
        if len(text) <= 1300
        else "Respond to the exact shared history, Bond, rank and conditioning "
        "shown on the preceding pages.",
        [
            Field(
                "decision",
                "Your own response",
                (("accept", "Accept this exact proposal"), ("decline", "Decline this proposal")),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_activation(
    interaction: discord.Interaction, service: HandlerCreationService
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))
    if not data["editable"] or data["missing"]:
        raise WorkflowError("Complete your original Handler draft before activation.")
    draft = Draft.model_validate_json(json.dumps(data["draft"]))
    names = {x["token"]: x["label"] for x in data["pilots"]}
    summary = "\nHandler: " + clean(draft.name) + "; " + str(draft.playbook)
    for choice in draft.starting:
        summary += (
            "\n"
            + clean(names.get(choice.pilot.token, "Original Girl"))
            + ": "
            + choice.rank.title()
            + ", "
            + ("Intense" if choice.depth == 2 else "Personal")
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.activate,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            data["game_revision"],
            True,
        )
        return "Handler activated. Starting Bonds, Status and mechanics are saved."

    form = NativeForm(
        interaction.user.id,
        "Activate your Handler",
        "Activation applies your saved starting Bond/rank choices and printed starting mechanics. "
        "All exact shared requests must be accepted. Existing stronger Bonds are preserved. "
        "Gear descriptions create no additional NPCs or vehicles." + summary,
        [
            Field(
                "confirm",
                "Your explicit confirmation",
                (("yes", "Activate this completed Handler"),),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
