"""Private owner-bound discipline selectors and explicit confirmations."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_punishments import KINDS, SUPPORTED, Details
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


class PickerSelect(discord.ui.Select["Picker"]):
    def __init__(self, parent: "Picker"):
        self.parent_picker = parent
        super().__init__(
            placeholder="Choose an item to review",
            row=0,
            options=[
                discord.SelectOption(value=value, label=label[:100])
                for value, label in parent.options[parent.page * 25 : parent.page * 25 + 25]
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if self.values[0] not in dict(self.parent_picker.options):
                raise WorkflowError("Choose an item from this current menu.")
            await self.parent_picker.open_item(interaction, self.values[0])
        except WorkflowError as error:
            await reply(interaction, str(error))


class Picker(discord.ui.View):
    def __init__(
        self,
        owner: int,
        title: str,
        options: tuple[tuple[str, str], ...],
        open_item: Callable[[discord.Interaction, str], Awaitable[None]],
    ):
        super().__init__(timeout=600)
        self.owner, self.title, self.options, self.open_item = owner, title, options, open_item
        self.page = 0
        self.controls()

    def controls(self) -> None:
        for item in list(self.children):
            if isinstance(item, PickerSelect):
                self.remove_item(item)
        if self.options:
            self.add_item(PickerSelect(self))
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 25 >= len(self.options)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This menu belongs to another participant.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        self.controls()
        await reply(
            interaction,
            self.title + f"\nPage {self.page + 1}. Select to review; no effect is applied yet.",
            self,
        )

    @discord.ui.button(label="Previous", row=1)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.defer()
        await self.show(interaction)

    @discord.ui.button(label="Next", row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.page = min(max(0, (len(self.options) - 1) // 25), self.page + 1)
        await interaction.response.defer()
        await self.show(interaction)


async def open_details(
    interaction: discord.Interaction, service: PunishmentService, identity: str, selection: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data.get("lobotomy_id") and data["state"] != "resolved":
        from girlframe.discord_adapter.m3_lobotomy import open_lobotomy
        from girlframe.services.m3_lobotomy import LobotomyService

        await open_lobotomy(interaction, LobotomyService(service.store), data["lobotomy_id"])
        return
    if data["owner_id"] != str(viewer.user_id) or "choices" not in data:
        raise WorkflowError("Reopen your current assigned discipline task.")
    kind, _, branch = selection.partition(":")
    if kind not in SUPPORTED:
        raise WorkflowError("UNSUPPORTED_RULE: this Punishment is not available yet.")
    own = data["choices"]

    def entities(
        key: str, label: str, entries: list[dict[str, Any]], minimum: int = 1, maximum: int = 1
    ) -> Field:
        if len(entries) < minimum:
            raise WorkflowError(
                "This Punishment has too few eligible choices; select another type."
            )
        return Field(
            key, label, tuple((x["id"], entity_label(x)) for x in entries), minimum, maximum
        )

    fields = []
    if kind == "sedation":
        count = min(2, len(own["identities"]))
        if count:
            fields.append(
                entities("identities", "Select Identities to mark", own["identities"], count, count)
            )
        else:
            fields.append(
                Field(
                    "confirm",
                    "No Identities remain; set Heat to zero",
                    (("yes", "Apply Sedation"),),
                )
            )
    elif kind in ("beating", "frame_disassembly", "compliance_surgery"):
        family = "frame" if kind == "frame_disassembly" else "girl"
        assets = [
            x
            for x in own["assets"]
            if x["family"] == family and (kind != "beating" or not x["damaged"])
        ]
        if kind == "beating":
            assets += own.get("body_parts", [])
        fields.append(entities("asset", "Choose the affected Asset or allowed part", assets))
        if kind == "compliance_surgery":
            fields.extend(
                [
                    Field("replacement_name", "Replacement Girl Asset name"),
                    Field("replacement_description", "Describe the replacement", paragraph=True),
                ]
            )
    elif kind == "revoked_privileges":
        fields.extend(
            [
                entities("requisition", "Temporarily remove this Requisition", own["requisitions"]),
                Field("restoration", "Condition for restoring it", paragraph=True),
            ]
        )
    elif kind == "reduced_socialization":
        if not own["bonds"]:
            raise WorkflowError("No eligible canonical Bond is available for this Punishment.")
        fields.append(Field("bond_with", "Weaken this Bond", tuple(own["bonds"])))
    elif kind == "passing_responsibility":
        fields.append(Field("delegate", "Choose the new inflictor", tuple(own["pilots"])))
    elif kind == "strict_regulations":
        fields.extend(
            [
                Field("regulation", "Describe the behavioural rule", paragraph=True),
                Field(
                    "disclosed",
                    "Inform the affected Girl?",
                    (("yes", "Inform her of the rule"), ("no", "Keep the rule concealed")),
                ),
            ]
        )
    elif kind == "correctional_programming":
        if branch == "embrace":
            fields.append(entities("embrace_tag", "Force this Tag to be embraced", own["tags"]))
            if own["identity_cap_reached"]:
                fields.append(
                    entities("identities", "Replace this Identity", own["removable_identities"])
                )
        elif branch == "erase":
            fields.append(
                entities("identities", "Remove this Identity", own["removable_identities"])
            )
        else:

            async def choose(current: discord.Interaction, value: str) -> None:
                await open_details(current, service, identity, kind + ":" + value)

            view = Picker(
                viewer.user_id,
                "Choose Correctional Programming's effect",
                (("erase", "Remove an Identity"), ("embrace", "Force a Tag to be embraced")),
                choose,
            )
            await view.show(interaction)
            return
    if kind in ("beating", "quality_time"):
        fields.append(Field("tag", "Write the inflicted Tag"))
    moderate_girl = KINDS[kind][1] == "moderate" and viewer.user_id != own["handler"]
    if moderate_girl:
        fields.append(
            Field(
                "operation",
                "Consult or apply approved proposal",
                (
                    ("consult", "Ask Handler to review these choices"),
                    ("apply", "Apply exactly approved choices"),
                ),
            )
        )
    if not fields:
        fields.append(
            Field("confirm", "Confirm the printed effect", (("yes", "Apply " + KINDS[kind][0]),))
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        details: dict[str, Any] = {"kind": kind}
        for field in fields:
            if field.key in ("operation", "confirm"):
                continue
            value = values[field.key]
            if field.key != "identities" and isinstance(value, tuple):
                value = value[0]
            if field.key in ("bond_with", "delegate"):
                value = int(value)
            if field.key == "disclosed":
                value = value == "yes"
            if field.key == "asset" and isinstance(value, str) and value.startswith("part:"):
                details["body_part"] = value.removeprefix("part:")
            else:
                details[field.key] = value
        operation = (
            service.consult
            if moderate_girl and values["operation"][0] == "consult"
            else service.apply
        )
        result = await asyncio.to_thread(
            operation,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            Details(**details),
        )
        return (
            "Saved: "
            + str(result["state"])
            + ". Reopen /mission discipline or /character requests for current work."
        )

    form = NativeForm(
        viewer.user_id,
        KINDS[kind][0] + " — " + data["callsign"],
        "The inflictor selects unspecified details. Explicit printed ownership overrides this. "
        + (
            "Each Off-Duty cause keeps its own actual Punishment. "
            if data.get("off_duty_id")
            else "One application covers this mission's failure and Dog causes. "
        )
        + "Review & Confirm commits the selected action.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_discipline(
    interaction: discord.Interaction, service: PunishmentService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data.get("lobotomy_id") and data["state"] != "resolved":
        from girlframe.discord_adapter.m3_lobotomy import open_lobotomy
        from girlframe.services.m3_lobotomy import LobotomyService

        await open_lobotomy(interaction, LobotomyService(service.store), data["lobotomy_id"])
        return
    if (
        data["state"] != "resolved"
        and data.get("context_scene")
        and data["owner_id"] != str(viewer.user_id)
    ):
        await open_context_scene(interaction, service, identity)
        return
    if data["state"] == "resolved" or data["owner_id"] != str(viewer.user_id):
        await reply(
            interaction,
            "Discipline for "
            + clean(data["callsign"])
            + ": "
            + data["state"]
            + ". Only the designated owner submits choices.",
        )
        return
    if data["kind"] == "punishment":

        async def choose(current: discord.Interaction, value: str) -> None:
            if value == "context_scene":
                await open_context_scene(current, service, identity)
                return
            await open_details(current, service, identity, value)

        view = Picker(
            viewer.user_id,
            "**Choose Punishment — "
            + clean(data["callsign"])
            + "**\n"
            + ", ".join(x.replace("_", " ") for x in data["causes"])
            + ".\nUnfinished printed types are unavailable.",
            (
                (("context_scene", "Record / confirm the Punishment scene"),)
                if data.get("off_duty_id")
                else ()
            )
            + tuple(
                (kind, KINDS[kind][0])
                for kind in KINDS
                if kind in SUPPORTED
                and (KINDS[kind][1] != "severe" or viewer.user_id == data["choices"]["handler"])
                and (
                    data.get("required_severity") is None
                    or KINDS[kind][1] == data["required_severity"]
                )
            ),
            choose,
        )
        await view.show(interaction)
        return
    if data["kind"] == "punishment_consult":
        fields = [
            Field(
                "approve",
                "Review this exact proposal",
                (("yes", "Approve this proposal"), ("no", "Decline; new review needed")),
            )
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.answer_consultation,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["approve"][0] == "yes",
            )
            return (
                "Consultation saved. The assigned inflictor must reopen and apply approved choices."
            )

        instructions = "\n".join(clean(x) for x in data["summary"])
        if data["stale"]:
            instructions += "\nState changed: decline and request a fresh proposal."
    elif data["kind"] == "punishment_helpless":
        fields = [
            Field(
                "inside_frame",
                "Actual body context when the last Girl Asset was lost",
                (("yes", "Inside a Frame"), ("no", "Outside a Frame")),
            ),
            Field("evidence", "Brief factual context", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.resolve_helpless,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                inside_frame=values["inside_frame"][0] == "yes",
                evidence=values["evidence"],
            )
            return "Context saved. " + (
                "Helplessness applied; explicit recovery is required."
                if result["helpless"]
                else "The outside-Frame Helplessness condition does not apply."
            )

        instructions = (
            "The last Girl Asset was damaged. Confirm the actual Frame context at that moment. "
            "Outside a Frame, the Pilot becomes Helpless."
        )
    elif data["kind"] == "punishment_frame_loss":
        fields = [
            Field(
                "piloting",
                "Was she piloting the Frame when the Asset was removed?",
                (("yes", "Piloting that Frame"), ("no", "Not piloting that Frame")),
            ),
            Field(
                "in_battle",
                "Was this loss in an actual battle?",
                (("yes", "In an actual battle"), ("no", "Outside battle")),
            ),
            Field("evidence", "Brief actual context", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.resolve_frame_loss,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                piloting=values["piloting"][0] == "yes",
                in_battle=values["in_battle"][0] == "yes",
                evidence=values["evidence"],
            )
            return (
                "Actual Defeat is required; its consequence remains pending."
                if result["defeat_required"]
                else "Actual context recorded; this loss does not require Defeat."
            )

        instructions = (
            "The last usable Frame Asset was removed. Confirm the actual source context. "
            "Losing it while piloting in battle requires Defeat."
        )
    elif data["kind"] == "punishment_paired_identity_heat":
        fields = [
            Field(
                "share", "Heat to share with your Pair", tuple((str(x), str(x)) for x in range(6))
            )
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.split_paired_heat,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                int(values["share"][0]),
            )
            return "Five Heat allocated once. Reopen your saved state or requests."

        instructions = "Your Paired Identity grants five Heat. You alone choose how much to share."
    else:
        from girlframe.discord_adapter.p1_facilitator import open_missing_work

        await open_missing_work(interaction, service.game, identity)
        return
    form = NativeForm(viewer.user_id, "Required discipline response", instructions, fields, submit)
    await reply(interaction, form.text(), form)


async def discipline_queue(interaction: discord.Interaction, service: PunishmentService) -> None:
    viewer = viewer_from_interaction(interaction)
    rows = await asyncio.to_thread(service.missions.owned_work, viewer)
    options = tuple(
        (x["id"], x["kind"].replace("_", " ").title() + " — Player " + x["subject_id"])
        for x in rows
        if x["kind"]
        in (
            "punishment",
            "punishment_consult",
            "punishment_paired_identity_heat",
            "punishment_helpless",
        )
    )
    if not options:
        await reply(
            interaction,
            "No supported discipline responses are assigned to you. "
            "Other required reactions remain in /character requests.",
        )
        return

    async def choose(current: discord.Interaction, identity: str) -> None:
        await open_discipline(current, service, identity)

    view = Picker(viewer.user_id, "**Your discipline work**", options, choose)
    await view.show(interaction)


async def open_context_scene(
    interaction: discord.Interaction, service: PunishmentService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] == "resolved" or not data.get("off_duty_id"):
        raise WorkflowError("Resume a pending Off-Duty Punishment.")
    scene = data.get("context_scene")
    if scene is None:
        if data["owner_id"] != str(viewer.user_id):
            raise WorkflowError("The inflictor sets this actual scene first.")
        fields = [Field("summary", "Brief Punishment scene account", paragraph=True)]
        instructions = (
            "Set the actual on-screen scene. Each participant must then confirm "
            "their own participation. This does not apply a Punishment."
        )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.propose_scene,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                values["summary"],
            )
            return (
                "Scene saved. Each participant confirms it through their requests "
                "before the Punishment is applied."
            )
    else:
        if (
            viewer.user_id not in scene["participants"]
            or viewer.user_id in scene["acknowledgements"]
        ):
            await reply(
                interaction,
                "Your participation is already recorded. Other participants answer for themselves.",
            )
            return
        fields = [
            Field(
                "confirm", "Your own participation", (("yes", "I confirm this scene was played"),)
            )
        ]
        instructions = (
            clean(scene["summary"]) + "\nConfirm only your own participation. "
            "Mechanical application remains with the inflictor."
        )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.attest_scene,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
            )
            return (
                "Your participation is saved. The inflictor must apply the actual "
                "Punishment; no one answers for another participant."
            )

    form = NativeForm(viewer.user_id, "Punishment scene", instructions, fields, submit)
    await reply(interaction, form.text(), form)
