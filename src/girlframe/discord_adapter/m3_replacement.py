"""Native proposal, package review and consent for compulsory free replacements."""

import asyncio
import json
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.fanbase import DEMOGRAPHICS, QUALITIES, Fanbase
from girlframe.engine.m3_frame_state import Package, Preferences, SuppliedAsset
from girlframe.engine.shared_setup import AM_ROLES
from girlframe.services.m3_replacement import COURT, PACKAGE, ROOTS, ReplacementService
from girlframe.services.onboarding import WorkflowError

YES_NO = (("yes", "Yes"), ("no", "No"))


def one(values: dict[str, Any], key: str) -> str:
    return str(values[key][0])


async def propose_form(
    interaction: discord.Interaction, service: ReplacementService, identity: str, frame: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if frame not in dict(data["frames"]):
        raise WorkflowError("Choose a different Frame from this current menu.")
    fields = [
        Field("frame_name", "Frame nickname (optional)", required=False),
        Field(
            "frame_appearance", "New Frame appearance (optional)", paragraph=True, required=False
        ),
    ]
    if frame == "THE PRINCE":
        fields += [
            Field(
                "demographics",
                "Two fan demographics",
                tuple((x, x) for x in DEMOGRAPHICS) + (("custom:1", "Custom demographic"),),
                2,
                2,
            ),
            Field(
                "demanded",
                "Two demanded qualities",
                tuple((x, x) for x in QUALITIES)
                + (("custom:1", "Custom quality 1"), ("custom:2", "Custom quality 2")),
                2,
                2,
            ),
            Field(
                "rejected",
                "Two rejected qualities",
                tuple((x, x) for x in QUALITIES)
                + (("custom:1", "Custom quality 1"), ("custom:2", "Custom quality 2")),
                2,
                2,
            ),
            Field("custom_demographic", "Custom demographic text", required=False),
            Field("custom_quality_1", "Custom quality 1 text", required=False),
            Field("custom_quality_2", "Custom quality 2 text", required=False),
        ]
    elif frame == "THE RED QUEEN":
        fields += [
            Field("court_role", "External Court role", tuple((x, x) for x in AM_ROLES)),
            Field(
                "court_target",
                "Ask this character to receive the AM",
                tuple((str(uid), label) for uid, label in data["people"]),
            ),
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        choices: dict[str, Any] = {
            "frame": frame,
            "frame_name": values.get("frame_name", ""),
            "frame_appearance": values.get("frame_appearance", ""),
        }
        if frame == "THE PRINCE":
            choices["fanbase"] = Fanbase(
                **{
                    k: values.get(k, () if k in ("demographics", "demanded", "rejected") else "")
                    for k in (
                        "demographics",
                        "demanded",
                        "rejected",
                        "custom_demographic",
                        "custom_quality_1",
                        "custom_quality_2",
                    )
                }
            )
        elif frame == "THE RED QUEEN":
            choices.update(
                court_role=one(values, "court_role"), court_target=int(one(values, "court_target"))
            )
        await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            Preferences(**choices),
        )
        return (
            "Proposal saved. The Handler specifies its free package; Court recipients answer "
            "their own requests. Reopen /mission replacement."
        )

    form = NativeForm(
        interaction.user.id,
        "Propose " + frame,
        "This saves your choices without installing the Frame. Changing your proposal needs "
        "a new package and Court responses. Compulsory replacement is free.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def package_form(
    interaction: discord.Interaction, service: ReplacementService, identity: str, count: int
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    frame = data["preferences"]["frame"]
    if not 0 <= count <= 5:
        raise WorkflowError("Choose a legal supplied Asset count.")
    options = tuple(
        (x, x)
        for x in sorted(
            {
                name
                for entry in CATALOG.values()
                if entry["family"] == "frame"
                for name in entry["assets"]
            }
        )
    ) + (("custom", "Custom Frame Asset"),)
    fields = []
    for index in range(count):
        fields += [
            Field(f"name{index}", f"Asset {index + 1} name", options),
            Field(f"custom{index}", f"Asset {index + 1} custom name", required=False),
            Field(f"description{index}", f"Asset {index + 1} description", paragraph=True),
            Field(f"damaged{index}", f"Asset {index + 1} starts damaged?", YES_NO),
            Field(f"void{index}", f"Asset {index + 1} starts Void-altered?", YES_NO),
        ]
    registry = service.missions.access.registry
    rules = (
        tuple(
            (x.id, x.title)
            for x in registry.entries
            if x.scope == "frame"
            and x.kind in ("play", "mechanic")
            and x.verified
            and x.module in registry.enabled_modules
        )
        if registry
        else ()
    )
    fields += [
        Field(
            "rules",
            "Extra unlocked abilities",
            (("none", "No extra unlocked abilities"),) + rules,
            1,
            min(25, len(rules) + 1),
        ),
        Field("explanation", "Explain this exact package", paragraph=True),
    ]
    if frame == "CONSUME":
        fields.append(
            Field(
                "consume_hunger",
                "Set CONSUME hunger",
                tuple((x, x) for x in ("Quiet", "Gnawing", "Ravenous")),
            )
        )
    elif frame == "DOCTORDOCTOR MK. II":
        fields.append(
            Field(
                "obsolescence",
                "Marked Obsolescence boxes",
                tuple((str(x), str(x)) for x in range(8)),
            )
        )
    elif frame == "CHANGELING" and data["bond_targets"]:
        fields.append(
            Field(
                "psych_strings",
                "Initial Psych Strings (none if empty)",
                tuple((str(uid), label) for uid, label in data["bond_targets"]),
                0,
                len(data["bond_targets"]),
                required=False,
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        def flag(key: str) -> bool:
            value = one(values, key)
            if value not in ("yes", "no"):
                raise WorkflowError("Choose Yes or No for each supplied Asset state.")
            return value == "yes"

        assets = tuple(
            SuppliedAsset(
                name=values.get(f"custom{i}", "")
                if one(values, f"name{i}") == "custom"
                else one(values, f"name{i}"),
                description=values[f"description{i}"],
                damaged=flag(f"damaged{i}"),
                void=flag(f"void{i}"),
            )
            for i in range(count)
        )
        selected_rules = values["rules"]
        if "none" in selected_rules and len(selected_rules) != 1:
            raise WorkflowError("Choose no extra abilities, or specific supported abilities.")
        supplied = Package(
            assets=assets,
            additional_rules=() if selected_rules == ("none",) else tuple(selected_rules),
            explanation=values["explanation"],
            consume_hunger=cast(
                Literal["Quiet", "Gnawing", "Ravenous"], one(values, "consume_hunger")
            )
            if "consume_hunger" in values
            else None,
            obsolescence_marked=int(one(values, "obsolescence"))
            if "obsolescence" in values
            else None,
            psych_strings=tuple(int(x) for x in values.get("psych_strings", ())),
        )
        await asyncio.to_thread(
            service.quote,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            supplied,
        )
        return (
            "Free package saved. The player must review and confirm it; "
            "no equipment or abilities have been installed yet."
        )

    form = NativeForm(
        interaction.user.id,
        "Handler replacement package",
        f"Supply exactly {count} ordinary Assets (up to five). "
        "WYVERN's printed Enormous Asset is additional and outside that limit. "
        "No Permissions are charged. Only available extra abilities can be added.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


class PackageReview(discord.ui.View):
    def __init__(self, owner: int, service: ReplacementService, data: dict[str, Any]):
        super().__init__(timeout=600)
        self.owner, self.service, self.data, self.page = owner, service, data, 0
        self.confirm.disabled = (
            data["kind"] not in ROOTS or data["subject_id"] != str(owner) or not data["ready"]
        )
        package = data["package"]
        selected = Preferences.model_validate_json(json.dumps(data["preferences"]))
        self.pages = [
            "**Exact replacement — "
            + clean(selected.frame)
            + "**\nPermission charge: 0.\n"
            + "Supplied Assets: "
            + str(len(package["assets"]))
            + (
                "\nPrinted additional intrinsic Asset: Enormous."
                if selected.frame == "WYVERN 0.4"
                else ""
            )
            + (
                "\nFurther consent or a fresh proposal is required."
                if not data["ready"]
                else "\nReview every page before confirming."
            ),
            "**Handler's exact package**\n" + clean(package["explanation"]),
        ]
        if data.get("firearm", {}).get("required"):
            self.pages.append(
                "**Personal Firearm**\nThis exact package issues one Girl pistol, "
                "with no Permission charge. Your ordinary Girl Asset limit still applies. "
                "If full, you choose one of your own non-Void Girl Assets at confirmation."
            )
        if selected.frame_name or selected.frame_appearance:
            self.pages.append(
                "**New Frame name and appearance**\n"
                + clean(selected.frame_name)
                + "\n"
                + clean(selected.frame_appearance)
            )
        for index, asset in enumerate(package["assets"]):
            self.pages.append(
                f"**Asset {index + 1} — {clean(asset['name'])}**\n"
                + clean(asset["description"])
                + "\nDamaged: "
                + str(asset["damaged"])
                + " · Void-altered: "
                + str(asset["void"])
            )
        lines = ["**Frame setup and additional abilities**"]
        if package["consume_hunger"]:
            lines.append("CONSUME hunger: " + package["consume_hunger"])
        if package["obsolescence_marked"] is not None:
            lines.append("Obsolescence boxes: " + str(package["obsolescence_marked"]))
        people = dict(data["people"])
        if package["psych_strings"]:
            lines.append(
                "Psych Strings: "
                + ", ".join(
                    clean(people.get(int(uid), "Character " + str(uid)))
                    for uid in package["psych_strings"]
                )
            )
        if selected.court_role:
            lines.append(
                "External Court role: "
                + selected.court_role
                + " → "
                + clean(people.get(selected.court_target, "Character"))
            )
            lines.append("Recipient accepted: " + str(data["court_accepted"]))
        if selected.fanbase:
            for field in ("demographics", "demanded", "rejected"):
                lines.append(
                    field.capitalize()
                    + ": "
                    + ", ".join(
                        clean(selected.fanbase.label(x, field == "demographics"))
                        for x in getattr(selected.fanbase, field)
                    )
                )
        registry = service.missions.access.registry
        labels = {x.id: x.title for x in registry.entries} if registry else {}
        lines += [
            "Additional ability: " + clean(labels.get(rule, "Saved Frame ability"))
            for rule in package["additional_rules"]
        ]
        if not package["additional_rules"]:
            lines.append("No extra unlocked abilities.")
        page = ""
        for line in lines:
            if len(page) + len(line) + 1 > 1900:
                self.pages.append(page)
                page = ""
            page += line + "\n"
        if page:
            self.pages.append(page)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This review belongs to another participant.")
            return False
        try:
            current = await asyncio.to_thread(
                self.service.get, viewer_from_interaction(interaction), self.data["id"]
            )
            if (
                current["revision"] != self.data["revision"]
                or current["game_revision"] != self.data["game_revision"]
            ):
                raise WorkflowError(
                    "This package or character state changed. Reopen /mission replacement."
                )
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page == len(self.pages) - 1
        await reply(interaction, self.pages[self.page], self)

    @discord.ui.button(label="Previous", row=1)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.defer()
        await self.show(interaction)

    @discord.ui.button(label="Next page", row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.page = min(len(self.pages) - 1, self.page + 1)
        await interaction.response.defer()
        await self.show(interaction)

    @discord.ui.button(
        label="Confirm this free replacement", style=discord.ButtonStyle.success, row=2
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        firearm = self.data.get("firearm") or {}
        if firearm.get("needs_replacement"):
            options = tuple((x["id"], x["label"]) for x in firearm["replacements"])
            if not options:
                await reply(
                    interaction,
                    "This pistol cannot fit your current Girl Assets. "
                    "Void Assets cannot be replaced. "
                    "Request a revised package; nothing was installed.",
                )
                return

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                replacement = one(values, "replace")
                if replacement not in {x[0] for x in options}:
                    raise WorkflowError("Reopen your current owned Girl Asset choices.")
                return await self.apply_package(current, replacement)

            form = NativeForm(
                self.owner,
                "Personal Firearm capacity",
                "Choose one of your own ordinary non-Void Girl Assets. "
                "The reviewed package and pistol are installed together once, for no Permissions.",
                [Field("replace", "Replace your actual Girl Asset", options)],
                submit,
            )
            await reply(interaction, form.text(), form)
            return
        try:
            message = await self.apply_package(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))
            return
        await reply(interaction, message)

    async def apply_package(
        self, interaction: discord.Interaction, firearm_replace: str | None = None
    ) -> str:
        await asyncio.to_thread(
            self.service.apply,
            viewer_from_interaction(interaction),
            str(interaction.id),
            self.data["id"],
            self.data["revision"],
            self.data["game_revision"],
            self.data["package_revision"],
            firearm_replace=firearm_replace,
        )
        self.stop()
        return (
            "Frame installed once, with no Permission charge. Discord labels are queued; "
            "/character sync can retry them. Reopen /mission inbox for remaining work."
        )


async def open_replacement(
    interaction: discord.Interaction, service: ReplacementService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] == "resolved":
        await reply(
            interaction, "This replacement task is resolved. Its recorded history is preserved."
        )
        return
    if data["kind"] == COURT:
        if data["owner_id"] != str(viewer.user_id):
            await reply(interaction, "The designated Court recipient must answer its own request.")
            return

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.answer_court,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                one(values, "accepted") == "yes",
            )
            return "Court response saved. The Frame owner must still confirm the exact package."

        form = NativeForm(
            viewer.user_id,
            "Replacement Court request",
            "Receive "
            + clean(data["role"])
            + " from "
            + clean(data["callsign"])
            + "'s proposed Red Queen? No role is assigned until the replacement is applied.",
            [Field("accepted", "Your response", YES_NO)],
            submit,
        )
        await reply(interaction, form.text(), form)
        return
    if data["kind"] == PACKAGE and data["owner_id"] == str(viewer.user_id):

        async def count(current: discord.Interaction, value: str) -> None:
            if value == "review":
                latest = await asyncio.to_thread(
                    service.get, viewer_from_interaction(current), identity
                )
                if latest["package"] is None:
                    raise WorkflowError("The package changed. Reopen this task.")
                review = PackageReview(current.user.id, service, latest)
                await review.show(current)
            else:
                await package_form(current, service, identity, int(value))

        limit = 5
        view = Picker(
            viewer.user_id,
            "Choose the exact supplied Asset count (compulsory replacement is free)",
            ((("review", "Review current package"),) if data["package"] else ())
            + tuple((str(i), str(i) + " supplied Assets") for i in range(limit + 1)),
            count,
        )
        await view.show(interaction)
        return
    if data["kind"] in ROOTS and data["owner_id"] == str(viewer.user_id):

        async def choose(current: discord.Interaction, value: str) -> None:
            if value == "review":
                latest = await asyncio.to_thread(
                    service.get, viewer_from_interaction(current), identity
                )
                if latest["package"] is None:
                    raise WorkflowError("The package changed. Reopen this task.")
                view = PackageReview(current.user.id, service, latest)
                await view.show(current)
            else:
                await propose_form(current, service, identity, value)

        options = (("review", "Review the exact quoted package"),) if data["package"] else ()
        options += tuple(data["frames"])
        view = Picker(
            viewer.user_id,
            "**Replace your scrapped Frame**\nReview a package, or choose a different Frame "
            "to propose/revise. No Permissions are charged.",
            options,
            choose,
        )
        await view.show(interaction)
        return
    if data["package"]:
        review = PackageReview(viewer.user_id, service, data)
        await review.show(interaction)
    else:
        await reply(
            interaction,
            "Waiting for the assigned participant's proposal or package. "
            "Reopen /mission replacement to refresh.",
        )


async def replacement_queue(interaction: discord.Interaction, service: ReplacementService) -> None:
    rows = await asyncio.to_thread(
        service.missions.owned_work, viewer_from_interaction(interaction)
    )
    options = tuple(
        (x["id"], x["kind"].replace("_", " ").title() + " — Player " + x["subject_id"])
        for x in rows
        if x["kind"] in (*ROOTS, PACKAGE, COURT)
    )
    if not options:
        await reply(interaction, "No compulsory replacement tasks are assigned to you.")
        return

    async def choose(current: discord.Interaction, identity: str) -> None:
        await open_replacement(current, service, identity)

    view = Picker(interaction.user.id, "**Compulsory Frame replacement**", options, choose)
    await view.show(interaction)
