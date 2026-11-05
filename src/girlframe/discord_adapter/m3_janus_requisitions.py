"""Actual JANUS acquisition and owned original Core treatment controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.m2_game import GameService
from girlframe.services.m3_janus_requisitions import JanusRequisitionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


async def available_actions(
    service: JanusRequisitionService, viewer: GuildViewer
) -> tuple[tuple[str, str], ...]:
    result = []
    try:
        menu = await asyncio.to_thread(service.menu, viewer)
    except (WorkflowError, ValueError):
        menu = {}
    if menu.get("rules"):
        result.append(("buy", "Acquire an available JANUS Requisition"))
    try:
        treatment = await asyncio.to_thread(service.tags, viewer)
    except (WorkflowError, ValueError):
        treatment = {}
    if treatment.get("tags"):
        result.append(("tags", "Treat an actual original Core Tag"))
    if treatment.get("trained"):
        result.append(("training", "Use Obedience Training"))
    from girlframe.services.m3_janus_pandora import menu as birth_menu
    from girlframe.services.m3_janus_pet import PetService

    try:
        birth = await asyncio.to_thread(birth_menu, service.game, viewer)
        if birth.get("can_birth"):
            result.append(("pandora", "Give birth from the actual Inseminated Frame"))
    except (WorkflowError, ValueError):
        pass
    with service.store.engine.connect() as connection:
        outings = PetService(service.game)._tasks(connection, viewer)
    result.extend(("pet:" + x["id"], "Actual Core outing: " + x["phase"]) for x in outings)
    from girlframe.services.m3_janus_storage import StorageService

    storage = await asyncio.to_thread(StorageService(service.game).view, viewer)
    if storage["points"]:
        result.append(("storage", "Review actual stored Void / request Foundation surgery"))
    return tuple(result)


async def open_janus_requisitions(
    interaction: discord.Interaction, service: JanusRequisitionService
) -> None:
    options = await available_actions(service, viewer_from_interaction(interaction))
    if not options:
        await reply(
            interaction,
            "No current reviewed JANUS acquisition or actual Core treatment is available.",
        )
        return

    async def choose(current: discord.Interaction, value: str) -> None:
        if value == "buy":
            await open_acquisition(current, service)
        elif value == "tags":
            await open_treatment(current, service)
        elif value == "training":
            await open_training(current, service)
        elif value == "pandora":
            await open_pandora(current, service.game)
        elif value.startswith("pet:"):
            await open_pet(current, service.game, value.removeprefix("pet:"))
        elif value == "storage":
            from girlframe.discord_adapter.m3_janus_storage import open_storage
            from girlframe.services.m3_janus_storage import StorageService

            await open_storage(current, StorageService(service.game))

    await Picker(
        interaction.user.id, "JANUS — actual Requisitions and Core care", options, choose
    ).show(interaction)


async def open_acquisition(
    interaction: discord.Interaction, service: JanusRequisitionService
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["rules"]:
        await reply(
            interaction, "No further reviewed JANUS Requisition is available for your actual Frame."
        )
        return
    price = 2 if data["kind"] == "ability_unlock" else 3

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.buy_rule,
            viewer_from_interaction(current),
            str(current.id),
            data["source_sha256"],
            values["rule"][0],
            values["account"],
        )
        return "Actual acquisition saved. Receipt: " + str(result["id"]) + "."

    await NativeForm(
        interaction.user.id,
        "Acquire a JANUS Requisition",
        "Your actual current Frame pays "
        + str(price)
        + " Permissions. Choose only an available rule.",
        [
            Field(
                "rule",
                "Available JANUS Requisition",
                tuple((x["id"], x["label"]) for x in data["rules"]),
            ),
            Field("account", "Describe your actual acquisition", paragraph=True),
            Field(
                "payment",
                "Confirm actual payment",
                (("yes", "Pay " + str(price) + " Permissions"),),
            ),
        ],
        submit,
    ).present(interaction)


async def open_treatment(
    interaction: discord.Interaction, service: JanusRequisitionService
) -> None:
    data = await asyncio.to_thread(service.tags, viewer_from_interaction(interaction))
    if not data["tags"]:
        await reply(interaction, "There are no remaining actual Core Tags to treat.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        result = await asyncio.to_thread(
            service.remove_tag,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            values["tag"][0],
            values["account"],
        )
        if result.get("void_work"):
            from girlframe.discord_adapter.m3_void import open_void
            from girlframe.services.m3_void import VoidService

            await open_void(current, VoidService(service.store), result["void_work"])
            return None
        return "Actual original Core Tag removed." + (
            " Its real Punishment request is in the Inbox." if result["punishment"] else ""
        )

    await NativeForm(
        interaction.user.id,
        "Treat the actual original Core",
        "Choose only a real existing Tag. The final Tag frees the Core, corrupts the "
        "original Frame, and always requires Punishment. "
        + (
            "Obedience Training prevents the ordinary removal Punishment."
            if data["trained"]
            else "Ordinary removal creates a real Punishment requirement."
        ),
        [
            Field("tag", "Actual Core Tag", tuple((x["id"], x["label"]) for x in data["tags"])),
            Field("account", "Describe the actual treatment", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_training(interaction: discord.Interaction, service: JanusRequisitionService) -> None:
    data = await asyncio.to_thread(service.tags, viewer_from_interaction(interaction))
    if not data["trained"]:
        raise WorkflowError("Acquire the actual reviewed Obedience Training rule first")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        result = await asyncio.to_thread(
            service.start_training,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            values["account"],
        )
        from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
        from girlframe.services.m3_role_punishments import RolePunishmentService

        await open_role_punishment(current, RolePunishmentService(service.game), result["id"])
        return None

    await NativeForm(
        interaction.user.id,
        "Obedience Training — actual Core",
        "Start your own real source scene. Actual choices and effects follow "
        "in their owned controls.",
        [
            Field("account", "Describe the actual training context", paragraph=True),
            Field(
                "confirm", "Start the source-owned scene", (("yes", "Continue to actual choices"),)
            ),
        ],
        submit,
    ).present(interaction)


async def open_pandora(interaction: discord.Interaction, game: GameService) -> None:
    from girlframe.services.m3_janus_pandora import menu

    data = await asyncio.to_thread(menu, game, viewer_from_interaction(interaction))
    if not data["can_birth"] or interaction.channel_id is None:
        raise WorkflowError("Use the actual Inseminated Frame in its source scene")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        assert current.channel_id is not None
        result = await asyncio.to_thread(
            game.begin,
            viewer_from_interaction(current),
            str(current.id),
            current.channel_id,
            data["sheet_revision"],
            PlayInput(
                play="pandora_birth",
                heat=int(values["heat"][0]),
                context=values["account"],
                trigger_confirmed=True,
            ),
        )
        return "Actual birth prepared. Action " + str(result["action_id"])

    await NativeForm(
        interaction.user.id,
        "PANDORA — actual birth",
        "Use your actual available Heat.",
        [
            Field("heat", "Heat", tuple((str(n), str(n)) for n in range(data["heat"] + 1))),
            Field("account", "Describe the actual birth", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_pandora_child(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    from girlframe.engine.m3_janus_pandora import ChildProposal

    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["janus"]

    async def identify(current: discord.Interaction, values: dict[str, Any]) -> None:
        names = detail["assets"][values["type"][0]]

        async def choose_assets(
            next_interaction: discord.Interaction, selected: dict[str, Any]
        ) -> None:
            assets = selected["assets"]

            async def finish(final: discord.Interaction, descriptions: dict[str, Any]) -> str:
                proposal = ChildProposal(
                    name=values["name"],
                    gorgon_type=values["type"][0],
                    gorgon_class=values["class"][0],
                    assets=tuple(assets),
                    descriptions=tuple(descriptions["asset" + str(n)] for n in range(len(assets))),
                    core_assets=tuple(int(n) for n in descriptions["core"]),
                    weakness=descriptions["weakness"],
                    account=values["account"],
                )
                await asyncio.to_thread(
                    game.respond,
                    viewer_from_interaction(final),
                    str(final.id),
                    identity,
                    data["revision"],
                    ChoiceAnswer(fields={"child": proposal.model_dump_json()}),
                )
                return "Actual newborn and source behavior saved."

            await NativeForm(
                next_interaction.user.id,
                "PANDORA — actual Assets and Core",
                detail["behavior"],
                [
                    *(
                        Field("asset" + str(n), name, paragraph=True)
                        for n, name in enumerate(assets)
                    ),
                    Field(
                        "core",
                        "Assets guarding the Core",
                        tuple((str(n), name) for n, name in enumerate(assets)),
                        minimum=1,
                        maximum=min(2, len(assets)),
                    ),
                    Field("weakness", "Actual weakness", paragraph=True),
                ],
                finish,
            ).present(next_interaction)

        await NativeForm(
            current.user.id,
            "PANDORA — printed Assets",
            "Choose the printed Asset count.",
            [
                Field(
                    "assets",
                    "Actual printed Assets",
                    tuple((name, name) for name in names),
                    minimum=detail["count"],
                    maximum=detail["count"],
                )
            ],
            choose_assets,
        ).present(current)

    await NativeForm(
        interaction.user.id,
        "PANDORA — describe the actual newborn",
        detail["behavior"],
        [
            Field("name", "Name"),
            Field(
                "class", "Actual result's Class", tuple((x, x.title()) for x in detail["classes"])
            ),
            Field("type", "Gorgon type", tuple((x, x.title()) for x in detail["types"])),
            Field("account", "Actual birth and behavior", paragraph=True),
        ],
        identify,
    ).present(interaction)


async def open_pet(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    from girlframe.services.m3_janus_pet import PetService

    service = PetService(game)
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    phase = data["outing"]["phase"]
    if not data["can_act"]:
        await reply(interaction, "Actual Core outing: " + phase + ". No action is currently yours.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        args = (viewer_from_interaction(current), str(current.id), identity, data["revision"])
        if phase == "choice":
            await asyncio.to_thread(
                service.decide, *args, values["choice"][0] == "carry", values["account"]
            )
        else:
            await asyncio.to_thread(service.return_core, *args, values["account"])
        return "Actual Core care saved."

    await NativeForm(
        interaction.user.id,
        "Pet — actual Core outing",
        "Carrying requires actual unplugging and reach. Returning requires the original Frame.",
        (
            [
                Field(
                    "choice",
                    "Actual outing",
                    (
                        ("carry", "Carry the actual Core"),
                        ("surgery", "Leave her for Foundation treatment"),
                    ),
                )
            ]
            if phase == "choice"
            else []
        )
        + [Field("account", "Describe the actual care or return", paragraph=True)],
        submit,
    ).present(interaction)
