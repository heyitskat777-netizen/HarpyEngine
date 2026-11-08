"""Private actual travel history; consequences use the original disclosed source."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_vatgrown_travel import VatgrownTravelService


async def _open_chaperoned(
    interaction: discord.Interaction,
    service: VatgrownTravelService,
    identity: str,
    data: dict[str, Any],
) -> None:
    viewer = viewer_from_interaction(interaction)

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

    text = "\n".join(
        (
            "**Actual chaperoned joint travel**",
            "Original route: "
            + clean(str(data["origin"]))
            + " → "
            + clean(str(data["destination"])),
            "Original owner's account: " + clean(data["owner_account"]),
            "Actual companion's account: " + clean(data["companion_account"] or "Not submitted"),
            "Journey result: " + clean(data["status"]),
            "Both bodies move when the invited companion accepts with their own movement account. "
            "The original owner may cancel before acceptance.",
        )
    )
    if data.get("closure_account") and data["status"] == "cancelled":
        text += "\nOriginal owner's cancellation: " + clean(data["closure_account"])
    if not (data["can_respond"] or data["can_cancel"]):
        history = MemoryHistory(viewer.user_id, text, access)
        await reply(interaction, history.text(), history)
        return
    options: list[tuple[str, str]] = []
    if data["can_respond"]:
        options.extend(
            (
                ("accept", "Authorize my movement; both move together"),
                ("decline", "Decline; neither body moves"),
            )
        )
    if data["can_cancel"]:
        options.append(("cancel", "Cancel my original proposal before acceptance"))
    fields = [
        Field("operation", "Your actual role's choice", tuple(options)),
        Field("account", "Your actual movement/accompaniment or closure account", paragraph=True),
    ]
    if data["can_respond"]:
        fields.append(
            Field(
                "mode",
                "If accepting: your own actual movement mode",
                (("body", "My actual body on foot"), ("frame", "My own Frame I actually pilot")),
                minimum=0,
                required=False,
            )
        )
        if data["mutual_required"]:
            fields.append(
                Field(
                    "mutual",
                    "Both Experiments: actual mutual accompaniment for this entire trip?",
                    (
                        ("yes", "I explicitly authorize actual mutual accompaniment"),
                        ("no", "I do not authorize mutual accompaniment"),
                    ),
                    minimum=0,
                    required=False,
                )
            )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        actual_viewer = viewer_from_interaction(current)
        if values["operation"] == ("cancel",):
            await asyncio.to_thread(
                service.cancel_chaperoned,
                actual_viewer,
                str(current.id),
                identity,
                data["revision"],
                values["account"],
            )
            return "Your original joint proposal is cancelled; neither body moved."
        accepted = values["operation"] == ("accept",)
        if accepted and len(values.get("mode", ())) != 1:
            from girlframe.services.onboarding import WorkflowError

            raise WorkflowError(
                "Select your actual movement mode before authorizing both movements"
            )
        await asyncio.to_thread(
            service.respond_chaperoned,
            actual_viewer,
            str(current.id),
            identity,
            data["revision"],
            accept=accepted,
            frame=values.get("mode") == ("frame",),
            account=values["account"],
            mutual=values.get("mutual") == ("yes",),
        )
        return (
            "Both actual original bodies moved together; the private receipt is saved."
            if accepted
            else "Your actual decline is saved; neither body moved."
        )

    form = MemoryForm(
        viewer.user_id, "Actual joint journey", text, fields, submit, authorize=access
    )
    await reply(interaction, form.text(), form)


async def open_vatgrown_travel(
    interaction: discord.Interaction,
    service: VatgrownTravelService,
    identity: str | None = None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        tasks = await asyncio.to_thread(service.menu, viewer)
        if not tasks:
            await reply(
                interaction,
                "Record an actual journey proposal or unchaperoned attempt "
                "through /campaign movement.",
            )
            return

        async def access_menu(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.menu, viewer_from_interaction(current))

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_vatgrown_travel(current, service, values["source"][0])

        menu = MemoryForm(
            viewer.user_id,
            "Your actual travel sources",
            "Private saved history and choices.",
            [Field("source", "Original source", tuple((x["id"], x["label"]) for x in tasks))],
            choose,
            authorize=access_menu,
        )
        await reply(interaction, menu.text(), menu)
        return

    data = await asyncio.to_thread(service.view, viewer, identity)
    if data.get("type") == "chaperoned":
        await _open_chaperoned(interaction, service, identity, data)
        return

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

    text = "\n".join(
        (
            "**Actual unchaperoned travel**",
            "Original route: "
            + clean(str(data["origin"]))
            + " → "
            + clean(str(data["destination"])),
            "Original account: " + clean(data["account"]),
            "Actual movement: " + ("Recorded" if data["performed_event"] else "Not performed"),
            "Explicit Handler disclosure: "
            + ("Recorded" if data["disclosed_event"] else "Not made"),
            "Optional Handler judgment: " + ("Recorded" if data["judgment_event"] else "Not made"),
        )
    )
    options = []
    if data["can_perform"]:
        options.append(("perform", "Actually perform the original movement"))
    if data["can_disclose"]:
        options.append(("disclose", "Explicitly disclose this source to the Handler"))
    if data["can_judge"]:
        options.append(("judge", "Open the existing optional Handler judgment"))
    if data["discipline"]:
        options.append(("discipline", "Open the actual chosen Punishment"))
    if not options:
        history = MemoryHistory(viewer.user_id, text, access)
        await reply(interaction, history.text(), history)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation = values["operation"][0]
        actual_viewer = viewer_from_interaction(current)
        if operation == "perform":
            await asyncio.to_thread(
                service.perform,
                actual_viewer,
                str(current.id),
                identity,
                data["revision"],
            )
            return "Actual movement saved. The rule evidence remains an unchaperoned departure."
        if operation == "disclose":
            await asyncio.to_thread(
                service.disclose,
                actual_viewer,
                str(current.id),
                identity,
                data["revision"],
                values.get("account", ""),
            )
            return "Your explicit private disclosure is saved. The Handler owns any judgment."
        if operation == "judge":
            from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
            from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService

            await open_vatgrown_plays(
                current,
                VatgrownPlaysService(service.game),
                data["violation"],
            )
            return None
        from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
        from girlframe.engine import m3_vatgrown_plays as vat
        from girlframe.services.m2_state import load_state
        from girlframe.services.m3_role_punishments import RolePunishmentService

        await asyncio.to_thread(service.view, actual_viewer, identity)
        with service.store.engine.connect() as c:
            state = load_state(c, service.store.campaign_id)
            discipline = vat.find(state, vat.Discipline, data["discipline"])
        await open_role_punishment(current, RolePunishmentService(service.game), discipline.case)
        return None

    form = MemoryForm(
        viewer.user_id,
        "Original travel source",
        text,
        [
            Field("operation", "Your actual source choice", tuple(options)),
            Field(
                "account",
                "Your explicit disclosure account (if disclosing)",
                paragraph=True,
                required=False,
            ),
        ],
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)
