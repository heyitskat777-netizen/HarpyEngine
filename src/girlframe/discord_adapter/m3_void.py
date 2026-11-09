"""Original-player honest questions and actual Handler consequences in private native forms."""

import asyncio
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_void import FINAL
from girlframe.services.m3_void import VoidService


async def _submit(
    service: VoidService,
    interaction: discord.Interaction,
    data: dict[str, Any],
    operation: Any,
    answer: dict[str, Any],
) -> str:
    result = await asyncio.to_thread(
        service.respond,
        viewer_from_interaction(interaction),
        str(interaction.id),
        data["id"],
        data["revision"],
        data["game_revision"],
        data["expected"],
        operation,
        answer,
    )
    return "Your actual response is saved. Reopen this request to continue. Stage: " + clean(
        result["stage"]
    )


class VoidMenu(discord.ui.View):
    def __init__(
        self,
        service: VoidService,
        data: dict[str, Any],
        owner: int,
        actions: tuple[tuple[str, str], ...],
    ):
        super().__init__(timeout=600)
        self.service, self.data, self.owner = service, data, owner
        control = VoidSelect(
            service,
            data,
            placeholder="Choose your actual next step",
            options=[discord.SelectOption(value=k, label=v) for k, v in actions],
        )
        self.add_item(control)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This private transformation belongs to another player.")
            return False
        return True


async def open_void(
    interaction: discord.Interaction,
    service: VoidService,
    identity: str,
    *,
    operation: str | None = None,
    asset_id: str | None = None,
    storage_controls: bool = True,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    stage = data["stage"]
    if storage_controls and operation is None and data.get("storage_unplug") and stage not in FINAL:
        from girlframe.discord_adapter.m3_punishments import Picker

        async def select(current: discord.Interaction, value: str) -> None:
            await open_void(
                current,
                service,
                identity,
                operation="storage_unplug" if value == "unplug" else None,
                storage_controls=False,
            )

        await Picker(
            interaction.user.id,
            "Actual stored-Void consequence",
            (
                ("continue", "Continue the actual Void consequence"),
                ("unplug", "Physically unplug the actual Harpy"),
            ),
            select,
        ).show(interaction)
        return
    if operation == "storage_unplug" and data.get("storage_unplug") and stage not in FINAL:
        from girlframe.services.m3_frame_control import FrameControlService

        async def unplug(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                FrameControlService(service.game).unplug,
                viewer_from_interaction(current),
                str(current.id),
                data["storage_unplug"],
                data["game_revision"],
                values["account"],
            )
            return "Actual neural unplug saved; only a ceased uncompleted Void cause can end."

        await NativeForm(
            interaction.user.id,
            "Unplug the actual stored Void source",
            "This does not remove permanent Void or undo any completed transformation.",
            [Field("account", "Describe the actual physical unplug", paragraph=True)],
            unplug,
        ).present(interaction)
        return
    if stage in FINAL and data["protection_active"]:
        if not data["guardian_owned"]:
            await reply(
                interaction,
                "This original Girl remains in the actual protective hold. "
                "Only the controller of her actual guardian can release it; "
                "her Void allure persists.",
            )
            return

        async def release(current: discord.Interaction, values: dict[str, Any]) -> str:
            return await _submit(
                service, current, data, "release_protection", dict(account=values["account"])
            )

        form = NativeForm(
            interaction.user.id,
            "Release actual protective hold",
            "Release only this actual hold. The original body stays where it is, with its "
            "current health and persistent Void allure. "
            "Future own-Frame entry triggers its real consequence.",
            [
                Field(
                    "confirm",
                    "Your actual guardian's choice",
                    (("release", "I actually let her go"),),
                ),
                Field("account", "Describe the actual release", paragraph=True),
            ],
            release,
        )
        await reply(interaction, form.text(), form)
        return
    if stage in FINAL:
        saved_defense = data.get("defensive_risk_use")
        await reply(
            interaction,
            "The actual original Void consequence is resolved: "
            + clean(stage)
            + "."
            + (
                "\nYour one-use Risk Factor lesson was used for this original source.\n"
                + clean(saved_defense["account"])
                if saved_defense
                else ""
            ),
        )
        return
    if stage == "resist_pending":
        from girlframe.discord_adapter.m3_void_keep import open_keep

        await open_keep(interaction, service.game, identity)
        return
    if data["question"] is not None and data["owner"]:

        async def answer(current: discord.Interaction, values: dict[str, Any]) -> str:
            return await _submit(
                service,
                current,
                data,
                "answer",
                dict(
                    answer=values["answer"][0] == "yes",
                    honest=True,
                    account="My honest answer to the actual Apometanoia question",
                ),
            )

        form = NativeForm(
            interaction.user.id,
            "Apometanoia: answer honestly",
            clean(data["question"]),
            [
                Field("answer", "Your actual honest answer", (("yes", "Yes"), ("no", "No"))),
                Field("honest", "Confirm honesty", (("honest", "This is my honest answer"),)),
            ],
            answer,
        )
        await reply(interaction, form.text(), form)
        return
    if operation is None:
        actions = []
        if data["owner"]:
            if data.get("defensive_risk_lessons"):
                actions.append(
                    ("use_risk_lesson", "Use an unused Risk Factor lesson for this source")
                )
            if stage == "physical_review":
                actions.append(("propose_occupancy", "Describe actual unknown cockpit occupancy"))
            if data["needs_free"]:
                actions.append(("begin", "Enter my affected Frame and begin Apometanoia"))
            if stage == "allured" and data.get("guardians"):
                actions.append(("protect", "Ask a present actual person to stop my entry"))
            if stage == "allured":
                actions.append(("propose_approach", "Record completed actual arrival and embrace"))
            if stage == "enclosed" and data["threshold"]["family"] == "frame":
                actions.append(("choose_escape", "Escape by damaging an actual Girl Asset"))
            if stage == "rebirth":
                actions.extend(
                    (
                        ("resources", "Choose what my new body retains"),
                        ("asset", "Rewrite an original Asset"),
                        ("rebirth", "Complete irreversible rebirth"),
                    )
                )
        if data["guardian_owned"] and stage == "allured":
            actions.append(("accept_protection", "Actually stop her entry and hold her outside"))
        if data["handler"]:
            if stage == "physical_review" and data["occupancy"]:
                actions.append(
                    ("confirm_occupancy", "Confirm the original body's actual occupancy")
                )
            if stage == "abandoned":
                actions.append(("abandoned", "Shape the actual unoccupied Frame as a Gorgon"))
            if stage == "allured" and data["approach"]:
                actions.append(("confirm_approach", "Confirm the Girl's completed actual arrival"))
            if data["pending_escape"] and stage == "enclosed":
                actions.append(("escape", "Shape the abandoned actual Frame as a Gorgon"))
            if stage == "overgrown":
                actions.append(("overgrown", "Record the consumed Girl's actual fate and Gorgon"))
        if not actions:
            await reply(
                interaction,
                "This source consequence awaits its actual owner's response. Stage: "
                + clean(stage),
            )
            return
        view = VoidMenu(service, data, interaction.user.id, tuple(actions))
        await reply(
            interaction,
            "**Actual Void consequence**\nStage: "
            + clean(stage)
            + ". Choices have real body, Asset and custody effects. "
            "Each person confirms only their own decision.",
            view,
        )
        return
    fields = []
    values: dict[str, Any] = {}
    text = "Record your actual owned choice; selections alone commit no effect."
    actual_operation = operation
    if operation == "use_risk_lesson":
        if not data["owner"] or not data.get("defensive_risk_lessons"):
            await reply(interaction, "This source has no eligible unused owned Risk lesson.")
            return
        fields = [
            Field(
                "lesson",
                "Your actual unused lesson",
                tuple((x["id"], x["label"]) for x in data["defensive_risk_lessons"]),
            ),
            Field(
                "account", "Your choice to use it for this actual Void consequence", paragraph=True
            ),
        ]
        text = (
            "Spend one unused Risk Factor lesson only for this original Void source. "
            "This adds no Void payment or dice. Inside your own all-Void Frame, "
            "you still owe a real Keep Your Head and the Handler's actual ruling. "
            "Continue the ordinary consequence instead to keep the lesson unused."
        )

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            return dict(lesson=v["lesson"][0], account=v["account"])
    elif operation == "propose_occupancy":
        fields = [
            Field(
                "mode",
                "The original body's actual occupancy",
                (
                    ("outside_frame", "Outside my own Frame"),
                    ("inside_frame", "Inside my own cockpit, not piloting"),
                    ("piloting", "Actually piloting my own Frame"),
                ),
            ),
            Field("account", "Describe the actual facts", paragraph=True),
        ]
        text = (
            "Actual map coordinates remain unknown. This establishes the original vessel and "
            "actual occupancy only after separate Handler confirmation. It does not move anyone."
        )

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            return dict(mode=v["mode"][0], account=v["account"])
    elif operation == "confirm_occupancy":
        fields = [
            Field(
                "confirm",
                "Confirm these actual original-body facts",
                (("confirm", "I confirm this actual occupancy"),),
            ),
            Field("account", "Actual independent factual confirmation", paragraph=True),
        ]
        text = (
            "Original owner's account: "
            + clean(data["occupancy"]["account"])
            + "\nOccupancy: "
            + clean(data["occupancy"]["mode"])
            + ". Unknown positions remain unknown. This grants no travel, healing or new body."
        )

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            return dict(account=v["account"])
    elif operation == "propose_approach":
        fields = [
            Field(
                "identity",
                "Your actual Identity to replace with Free",
                tuple((x["id"], x["name"]) for x in data["identities"]),
            ),
            Field("account", "Describe actual completed arrival/embrace", paragraph=True),
        ]
        text = (
            "Record the actual completed stage-one arrival and embrace for separate "
            "Handler confirmation. The original body and actual Frame are preserved; "
            "unknown map coordinates remain unknown."
        )

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            return dict(identity=v["identity"][0], account=v["account"])
    elif operation == "confirm_approach":
        fields = [
            Field(
                "confirm",
                "Verify actual completed arrival and entry",
                (("confirm", "She actually reached and entered this Frame"),),
            ),
            Field("account", "Actual independent factual confirmation", paragraph=True),
        ]
        text = (
            "Original owner's account: "
            + clean(data["approach"]["account"])
            + "\nChosen Identity replaced with Free: "
            + clean(data["approach"]["identity_name"])
            + ". Confirm the actual completed facts."
        )

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            return dict(account=v["account"])
    elif operation == "begin":
        fields = [
            Field(
                "identity",
                "Choose the original Identity to replace with Free",
                tuple((x["id"], x["name"]) for x in data["identities"]),
            ),
            Field("account", "Describe your actual entry or embrace", paragraph=True),
        ]

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            return dict(identity=v["identity"][0], account=v["account"])
    elif operation == "choose_escape":
        options = tuple(
            (x["id"], x["name"])
            for x in data["assets"]
            if x["family"] == "girl" and not x["damaged"]
        )
        if not options:
            await reply(
                interaction,
                "This printed escape needs an undamaged Girl Asset; none is currently available.",
            )
            return
        fields = [
            Field("asset", "Choose the actual Girl Asset to damage", options),
            Field("account", "Describe your chosen escape", paragraph=True),
        ]

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            return dict(asset=v["asset"][0], account=v["account"])
    elif operation == "protect":
        actors = {str(i): x for i, x in enumerate(data["guardians"])}
        fields = [
            Field(
                "guardian",
                "Choose a present actual protector",
                tuple((k, x["label"]) for k, x in actors.items()),
            ),
            Field("account", "Your actual request for help", paragraph=True),
        ]

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            return dict(guardian=actors[v["guardian"][0]]["ref"], account=v["account"])
    elif operation == "accept_protection":
        fields = [
            Field(
                "confirm",
                "Your actual physical intervention",
                (("hold", "I actually stop her and hold her outside"),),
            ),
            Field("account", "Describe your actual protective hold", paragraph=True),
        ]

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            return dict(account=v["account"])
    elif operation in ("escape", "overgrown", "abandoned"):
        gorgon_identity = str(uuid4())
        classes = ["aggressive", "dormant", "erratic", "benevolent"]
        if data["gorgon_goals"]:
            classes.append("directed")
        if data["gorgon_leaders"]:
            classes.append("sprite")
        fields = [
            Field("name", "Name this actual Gorgon"),
            Field(
                "class",
                "Actual Gorgon Class",
                tuple((x, x.title()) for x in classes),
            ),
            Field(
                "types",
                "Actual Gorgon Types",
                tuple(
                    (x, x.title())
                    for x in (
                        "incubus",
                        "doppleganger",
                        "jackdaw",
                        "mother",
                        "sentinel",
                        "leviathan",
                        "growth",
                        "parasite",
                    )
                ),
                maximum=8,
            ),
            Field(
                "core",
                "Actual Assets protecting its Core",
                tuple((x["id"], x["name"]) for x in data["frame_assets"]),
                maximum=min(2, len(data["frame_assets"])),
            ),
            Field("weakness", "Actual Core exposure weakness", paragraph=True),
        ]
        if data["gorgon_goals"]:
            fields.extend(
                (
                    Field(
                        "goal",
                        "Directed only: its actual goal",
                        tuple((x["id"], x["name"]) for x in data["gorgon_goals"]),
                        required=False,
                    ),
                    Field(
                        "protected_asset",
                        "Directed only: its actual protective Asset",
                        tuple((x["id"], x["name"]) for x in data["frame_assets"]),
                        required=False,
                    ),
                )
            )
        if data["gorgon_leaders"]:
            fields.extend(
                (
                    Field(
                        "follows",
                        "Sprite only: actual Gorgon followed",
                        tuple((x["id"], x["name"]) for x in data["gorgon_leaders"]),
                        required=False,
                    ),
                    Field(
                        "sprite_group",
                        "Sprite only: actual group",
                        (("no", "A single actual Sprite"), ("yes", "An actual group of Sprites")),
                        required=False,
                    ),
                )
            )
        if operation == "overgrown":
            fields.append(
                Field(
                    "alive",
                    "Observed uncertain survival",
                    (("alive", "Alive, consumed and trapped"), ("dead", "Actually died")),
                )
            )
        fields.append(Field("account", "Actual Handler consequence", paragraph=True))
        text = (
            "The actual original Frame keeps its real Asset identities and known or unknown "
            "position. Consumed survivors remain injured and trapped; "
            "this does not heal or release anyone."
        )

        def payload(v: dict[str, Any]) -> dict[str, Any]:
            extra = {}
            if v["class"][0] == "directed":
                actual_goal = next(x for x in data["gorgon_goals"] if x["id"] == v["goal"][0])
                extra = dict(
                    goal={
                        k: val
                        for k, val in actual_goal.items()
                        if k in ("kind", "cell", "entity_id")
                    },
                    protected_asset=v["protected_asset"][0],
                )
            if v["class"][0] == "sprite":
                extra = dict(follows=v["follows"][0], sprite_group=v["sprite_group"][0] == "yes")
            return dict(
                account=v["account"],
                alive=v.get("alive", ("alive",))[0] == "alive",
                gorgon=dict(
                    id=gorgon_identity,
                    name=v["name"],
                    cell=data["frame_cell"],
                    gorgon_class=v["class"][0],
                    types=list(v["types"]),
                    assets=[
                        dict(
                            id=x["id"],
                            family="gorgon",
                            name=x["name"],
                            description=x["description"]
                            or "Original Frame Asset; exact nature described by the actual Handler",
                            damaged=x["damaged"],
                            void=True,
                        )
                        for x in data["frame_assets"]
                    ],
                    core_plan=dict(assets=list(v["core"]), weakness=v["weakness"]),
                    **extra,
                ),
            )
    elif operation in ("resources", "asset", "rebirth"):
        choice = data["rebirth_choice"]
        if operation == "asset" and asset_id is None:
            asset_menu = AssetMenu(service, data, interaction.user.id)
            await reply(
                interaction,
                "Choose an original Asset to rewrite for your actual new body.",
                asset_menu,
            )
            return
        if operation == "resources":
            for key, label, records in (
                ("retained_identities", "Keep these Identities", data["identities"]),
                ("retained_tags", "Keep these Tags", data["tags"]),
                ("retained_plays", "Keep these former Plays", data["plays"]),
            ):
                if records:
                    fields.append(
                        Field(
                            key,
                            label,
                            tuple(
                                (x["id"], x.get("name", x.get("label", "Actual resource")))
                                for x in records
                            ),
                            minimum=0,
                            maximum=len(records),
                            required=False,
                        )
                    )
                    values[key] = tuple(choice[key])
            peers = {str(i): x for i, x in enumerate(data["bonds"])}
            if peers:
                fields.append(
                    Field(
                        "discarded_bonds",
                        "Discard these actual Bonds (others remain)",
                        tuple(
                            (k, "Actual Bond: " + x["ref"]["kind"] + ":" + x["ref"]["entity"])
                            for k, x in peers.items()
                        ),
                        minimum=0,
                        maximum=len(peers),
                        required=False,
                    )
                )
                values["discarded_bonds"] = tuple(
                    k for k, x in peers.items() if x["ref"] in choice["discarded_bonds"]
                )
            fields.extend(
                (
                    Field(
                        "new_identities",
                        "New Identities, one per line",
                        paragraph=True,
                        required=False,
                    ),
                    Field("account", "Describe your actual retained self", paragraph=True),
                )
            )
            values["new_identities"] = "\n".join(choice["new_identities"])
            actual_operation = "save_rebirth"

            def payload(v: dict[str, Any]) -> dict[str, Any]:
                changed = choice | dict(
                    retained_identities=list(v.get("retained_identities", ())),
                    retained_tags=list(v.get("retained_tags", ())),
                    retained_plays=list(v.get("retained_plays", ())),
                    new_identities=[
                        x.strip() for x in v.get("new_identities", "").splitlines() if x.strip()
                    ],
                    discarded_bonds=[peers[k]["ref"] for k in v.get("discarded_bonds", ())],
                    account=v["account"],
                )
                return dict(choice=changed, account=v["account"])
        elif operation == "asset":
            asset = next(x for x in choice["assets"] if x["id"] == asset_id)
            fields = [
                Field("name", "Your rewritten Asset name"),
                Field("description", "Your actual rewritten Asset", paragraph=True, required=False),
                Field("account", "Describe this owned rewrite", paragraph=True),
            ]
            values = dict(name=asset["name"], description=asset["description"])
            actual_operation = "save_rebirth"

            def payload(v: dict[str, Any]) -> dict[str, Any]:
                changed = choice | dict(
                    assets=[
                        x | dict(name=v["name"], description=v.get("description", ""))
                        if x["id"] == asset_id
                        else x
                        for x in choice["assets"]
                    ]
                )
                return dict(choice=changed, account=v["account"])
        else:
            fields = [
                Field(
                    "confirm",
                    "This actual transformation cannot be undone",
                    (("confirm", "Complete my chosen irreversible rebirth"),),
                ),
                Field("account", "My actual rebirth", paragraph=True),
            ]
            text = (
                "Saved choices: "
                + str(len(choice["retained_identities"]))
                + " former Identities, "
                + str(len(choice["retained_tags"]))
                + " Tags, "
                + str(len(choice["retained_plays"]))
                + " former Plays. The original career is archived; "
                "this actual Harpy remains your distinct character. "
                "Harpy advancement choices remain separately owed."
            )

            def payload(v: dict[str, Any]) -> dict[str, Any]:
                return dict(choice=choice | dict(account=v["account"]), account=v["account"])
    else:
        await reply(interaction, "Reopen the actual source request to choose your next step.")
        return

    async def submit(current: discord.Interaction, answer: dict[str, Any]) -> str:
        return await _submit(service, current, data, actual_operation, payload(answer))

    form = NativeForm(
        interaction.user.id, "Original-source Void consequence", text, fields, submit, values=values
    )
    await reply(interaction, form.text(), form)


class AssetMenu(discord.ui.View):
    def __init__(self, service: VoidService, data: dict[str, Any], owner: int):
        super().__init__(timeout=600)
        self.owner = owner
        select = VoidSelect(
            service,
            data,
            asset=True,
            options=[
                discord.SelectOption(value=x["id"], label=x["name"][:100])
                for x in data["rebirth_choice"]["assets"]
            ],
        )
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "Only the original owner rewrites these actual Assets.")
            return False
        return True


class VoidSelect(discord.ui.Select[Any]):
    def __init__(
        self, service: VoidService, data: dict[str, Any], *, asset: bool = False, **kwargs: Any
    ):
        super().__init__(**kwargs)
        self.service, self.data, self.asset = service, data, asset

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await open_void(
            interaction,
            self.service,
            self.data["id"],
            operation="asset" if self.asset else self.values[0],
            asset_id=self.values[0] if self.asset else None,
        )
