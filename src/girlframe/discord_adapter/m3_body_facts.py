"""Private factual setup for actual bodies, independent of the owner's Frame menu."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.onboarding import WorkflowError


async def open_body_facts(
    interaction: discord.Interaction, service: BodyFactsService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is not None:
        shown = await asyncio.to_thread(service.view, viewer, identity)
        fact = shown["fact"]

        async def read(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

        if shown.get("kind") == "npc_original_body":
            text = "\n".join(
                (
                    "**Original starting NPC body evidence**",
                    "Original person: " + clean(fact["subject"]),
                    "Original Frame: " + clean(fact["frame"]),
                    "Starting role: " + str(fact["slot"]),
                    "Original source: " + clean(fact["start_event"]),
                    "Existing vessel: " + clean(fact["vessel"]),
                    "Existing brain: " + clean(fact["brain"]),
                    "Actual Handler's positive account: " + clean(fact["account"]),
                    "Saved factual source: " + clean(fact["event"]),
                )
            )
        else:
            text = "\n".join(
                (
                    "**Your saved factual body account**",
                    "Actual role: " + clean(fact["actor"]),
                    "Kind: " + clean(fact["kind"]),
                    "Original vessel: " + clean(fact["vessel"]),
                    "Original brain: " + clean(fact["brain"]),
                    "Actual account: " + clean(fact["account"]),
                    "Saved source: " + clean(fact["event"]),
                )
            )
        history = MemoryHistory(viewer.user_id, text, read)
        await reply(interaction, history.text(), history)
        return
    channel = int(interaction.channel_id or 0)
    menu = await asyncio.to_thread(service.menu, viewer, channel)
    options = [("history:" + row["id"], row["label"]) for row in menu["tasks"]]
    options.extend(
        ("body:" + str(index), "Record body: " + row["label"])
        for index, row in enumerate(menu["actors"])
        if not row["proved"] and row["joined"]
    )
    options.extend(
        ("import:" + str(index), "Import verified starting subset (" + str(row["eligible"]) + ")")
        for index, row in enumerate(menu["imports"])
        if row.get("pending") and row.get("ready")
    )
    options.extend(
        ("npc-original:" + str(index), "Establish original NPC body: " + row["label"])
        for index, row in enumerate(menu["npc_originals"])
        if not row["gap"]
    )
    if any(not row["joined"] and not row["proved"] for row in menu["actors"]):
        options.append(("cast", "Choose your actual scene role"))
    gaps = [row["gap"] for row in menu["imports"] if row.get("gap")]
    gaps.extend(
        subject["gap"]
        for row in menu["imports"]
        for subject in row.get("subjects", ())
        if subject.get("gap")
    )
    gaps.extend(row["gap"] for row in menu["npc_originals"] if row["gap"])
    instructions = (
        "Record factual game evidence for an existing actual body. "
        "This does not create a body or consent."
    )
    if gaps:
        instructions += "\nRequired original source evidence:\n" + "\n".join(gaps)
    if not options:

        async def refresh(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.menu, viewer_from_interaction(current), channel)

        history = MemoryHistory(viewer.user_id, clean(instructions), refresh)
        await reply(interaction, history.text(), history)
        return

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.menu, viewer_from_interaction(current), channel)

    async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        token = values["entry"][0]
        if token.startswith("history:"):
            await open_body_facts(current, service, token.removeprefix("history:"))
            return None
        if token == "cast":
            from girlframe.discord_adapter.m3_cast import open_cast
            from girlframe.services.m3_actors import ActorService
            from girlframe.services.m3_cast import CastService
            from girlframe.services.m3_missions import MissionService

            await open_cast(current, CastService(ActorService(MissionService(service.store))))
            return None
        if token.startswith("npc-original:"):
            row = menu["npc_originals"][int(token.removeprefix("npc-original:"))]

            async def establish(response: discord.Interaction, answers: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.establish_npc_original,
                    viewer_from_interaction(response),
                    str(response.id),
                    menu["revision"],
                    channel,
                    ActorRef.model_validate(row["owner"]),
                    row["slot"],
                    answers["account"],
                )
                return (
                    "The positive original-body evidence is saved. "
                    "The original Frame owner can now review and import "
                    "the verified starting source."
                )

            form = MemoryForm(
                viewer.user_id,
                "Original starting NPC body",
                "Actual NPC: "
                + row["label"]
                + "\nOriginal Frame: "
                + row["frame"]
                + "\nOriginal starting source: "
                + row["start_event"]
                + "\nRecord positive factual evidence that this exact existing brain/body "
                "belongs to the original saved starting-role person at that Frame start "
                "and actual introduction. If this is unknown, leave it unresolved. "
                "This records neither consent nor a String grant.",
                [Field("account", "Actual Handler's original-body evidence", paragraph=True)],
                establish,
                authorize=access,
            )
            await reply(current, form.text(), form)
            return None
        if token.startswith("import:"):
            row = menu["imports"][int(token.removeprefix("import:"))]

            async def repair(response: discord.Interaction, answers: dict[str, Any]) -> str:
                result = await asyncio.to_thread(
                    service.import_starting,
                    viewer_from_interaction(response),
                    str(response.id),
                    menu["revision"],
                    ActorRef.model_validate(row["actor"]),
                    row["source_event"],
                )
                return (
                    str(result["imported"])
                    + " independently verified starting String(s) imported. "
                    + str(len(result["unresolved"]))
                    + " original source(s) remain unresolved; "
                    "reopen Actual bodies to review their evidence gaps. Spent Strings stay spent."
                )

            form = MemoryForm(
                viewer.user_id,
                "Import verified starting subset",
                "Frame: "
                + row["frame"]
                + "\nOriginal source: "
                + row["source_event"]
                + "\nIndependently verified: "
                + str(row["eligible"])
                + "\nVerified people: "
                + ", ".join(
                    subject["label"]
                    for subject in row["subjects"]
                    if not subject["imported"] and not subject["gap"]
                )
                + "\nUnresolved sources remain pending: "
                + str(len(row["unresolved"]))
                + "\n"
                + "\n".join(
                    str(subject.get("label", subject["reference"])) + ": " + str(subject["gap"])
                    for subject in row["unresolved"]
                ),
                [
                    Field(
                        "confirm",
                        "Explicit owner repair",
                        (("yes", "Import only this verified subset"),),
                    )
                ],
                repair,
                authorize=access,
            )
        elif token.startswith("body:"):
            row = menu["actors"][int(token.removeprefix("body:"))]

            async def record(response: discord.Interaction, answers: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.record,
                    viewer_from_interaction(response),
                    str(response.id),
                    menu["revision"],
                    channel,
                    ActorRef.model_validate(row["actor"]),
                    answers["kind"][0],
                    answers["account"],
                )
                return (
                    "The actual original body and human-authored factual account "
                    "are saved privately."
                )

            form = MemoryForm(
                viewer.user_id,
                "Actual body facts",
                row["label"],
                [
                    Field(
                        "kind", "Actual body category", tuple((kind, kind) for kind in row["kinds"])
                    ),
                    Field("account", "Actual original body/brain evidence", paragraph=True),
                ],
                record,
                authorize=access,
            )
        else:
            raise WorkflowError(
                "Choose an actual body or proved original source from your own view"
            )
        await reply(current, form.text(), form)
        return None

    form = MemoryForm(
        viewer.user_id,
        "Actual bodies",
        instructions,
        [Field("entry", "Your actual source controls", tuple(options))],
        select,
        authorize=access,
    )
    await reply(interaction, form.text(), form)
