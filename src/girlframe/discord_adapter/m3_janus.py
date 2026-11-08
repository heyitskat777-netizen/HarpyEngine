"""Private original-controller JANUS Core setup; no personal-name or copied PC form."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_janus_state import CoreFacts
from girlframe.engine.m3_void_state import HarpyAsset, HarpyIdentity
from girlframe.services.m3_janus import JanusService
from girlframe.services.onboarding import WorkflowError


async def open_core_setup(
    interaction: discord.Interaction, service: JanusService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        candidates = await asyncio.to_thread(service.candidates, viewer)

        async def request(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.request,
                viewer_from_interaction(current),
                str(current.id),
                int(values["controller"][0]),
            )
            return (
                "Original Core setup requested. The selected real controller supplies factual "
                "resources privately, then the Foundation source judge reviews them. "
                "Reopen /mission inbox for setup " + str(result["id"]) + "."
            )

        form = NativeForm(
            viewer.user_id,
            "Register your original JANUS Core",
            "The Core is a distinct, unnamed ex-Girl attached to your existing JANUS. "
            "Choose her real human controller. This grants no other PC's sheet, "
            "invented past history or paid abilities.",
            [
                Field("controller", "Actual Core human controller", tuple(candidates)),
                Field("confirm", "Original source setup", (("yes", "Request this setup"),)),
            ],
            request,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.get, viewer, identity)
    setup = data["setup"]
    if setup["phase"] in ("admitted", "declined", "withdrawn"):
        await reply(
            interaction, "Original Core setup " + setup["phase"] + ". Its actual source is saved."
        )
        return
    if setup["phase"] == "controller" and data["controller"]:

        async def choose(current: discord.Interaction, value: str) -> None:
            if value == "withdraw":
                await open_core_withdraw(current, service, identity)
            else:
                await open_core_facts(current, service, identity, int(value))

        await Picker(
            viewer.user_id,
            "How many actual existing Girl Assets does the Core have?",
            tuple((str(n), str(n) + " actual existing Girl Assets") for n in range(5))
            + (("withdraw", "Withdraw this source admission"),),
            choose,
        ).show(interaction)
        return
    if setup["phase"] == "review" and data["judge"]:

        async def review(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.change,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                approve=values["approve"][0] == "yes",
                account=values["account"],
            )
            return (
                "Actual source review saved; no new Frame, former PC or paid ability was created."
            )

        form = NativeForm(
            viewer.user_id,
            "Review original Core facts",
            "Approve only established original ex-Girl facts. "
            "The same existing JANUS Frame Assets remain their sole authority.\n"
            + str(setup["facts"]),
            [
                Field(
                    "approve",
                    "Actual Foundation source review",
                    (("yes", "Approve established facts"), ("no", "Decline this proposal")),
                ),
                Field("account", "Actual factual source review", paragraph=True),
            ],
            review,
        )
        await reply(interaction, form.text(), form)
        return
    if viewer.user_id in (int(setup["owner"]["entity"]), setup["controller"]):
        await open_core_withdraw(interaction, service, identity)
        return
    await reply(
        interaction,
        "The original controller or Foundation source judge has the next setup response.",
    )


async def open_core_facts(
    interaction: discord.Interaction, service: JanusService, identity: str, count: int
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if not data["controller"] or data["setup"]["phase"] != "controller" or not 0 <= count <= 4:
        raise WorkflowError(
            "Only the original selected Core controller supplies existing body facts"
        )
    fields = [
        Field("appearance", "Known original Core body appearance", paragraph=True),
        Field("heat", "Actual current Heat (whole number)"),
        Field(
            "identities",
            "Known original Identities, one per line; blank if none",
            paragraph=True,
            required=False,
        ),
        Field(
            "exposed",
            "Is the actual Core currently exposed?",
            (("yes", "Actually exposed"), ("no", "Not exposed")),
        ),
        Field("account", "Source for these established original facts", paragraph=True),
    ]
    for n in range(count):
        fields += [
            Field("name" + str(n), "Existing Girl Asset " + str(n + 1)),
            Field("description" + str(n), "Describe the actual existing Asset", paragraph=True),
            Field(
                "damaged" + str(n),
                "Actual current damage",
                (("yes", "Damaged"), ("no", "Undamaged")),
            ),
        ]

    async def save(current: discord.Interaction, values: dict[str, Any]) -> str:
        try:
            heat = int(values["heat"])
        except ValueError:
            raise WorkflowError("Record actual Heat as a whole nonnegative number") from None
        names = [x.strip() for x in values.get("identities", "").splitlines() if x.strip()]
        facts = CoreFacts(
            appearance=values["appearance"],
            heat=heat,
            identities=tuple(
                HarpyIdentity(id=identity + ":identity:" + str(n), name=name)
                for n, name in enumerate(names)
            ),
            girl_assets=tuple(
                HarpyAsset(
                    id=identity + ":girl:" + str(n),
                    family="girl",
                    name=values["name" + str(n)],
                    description=values["description" + str(n)],
                    damaged=values["damaged" + str(n)][0] == "yes",
                    void=True,
                )
                for n in range(count)
            ),
            exposed=values["exposed"][0] == "yes",
            account=values["account"],
            facts_confirmed=True,
        )
        await asyncio.to_thread(
            service.change,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            facts=facts,
        )
        return (
            "Your actual original Core facts are saved for Foundation review. "
            "The Core remains unnamed."
        )

    form = NativeForm(
        viewer.user_id,
        "Actual original Core facts",
        "Supply established ex-Girl resources, not a copied PC or new free gear. "
        "Normal Harpy Girl Assets are Void; the shared JANUS Frame retains its actual Assets.",
        fields,
        save,
    )
    await reply(interaction, form.text(), form)


async def open_janus(interaction: discord.Interaction, service: JanusService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.menu, viewer)
    options = [
        ("setup:" + x["id"], "Original Core setup — " + x["phase"])
        for x in data["tasks"]
        if x["phase"] in ("controller", "review")
    ]
    if data["can_request"]:
        options.insert(0, ("request", "Register actual original Core"))
    from girlframe.services.m3_janus_play import preview as battery_preview

    battery = await asyncio.to_thread(
        battery_preview, service.game, viewer, int(interaction.channel_id or 0)
    )
    if battery["available"]:
        options.append(("battery", "Living Battery — actual contact and roll"))
    from girlframe.services.m3_janus_play import BatteryService

    with service.store.engine.connect() as c:
        minds = BatteryService(service.game)._tasks(c, viewer)
    options.extend(("mind:" + x["id"], "Your private brain link") for x in minds)
    from girlframe.discord_adapter.m3_janus_requisitions import available_actions
    from girlframe.services.m3_janus_requisitions import JanusRequisitionService

    if await available_actions(JanusRequisitionService(service.game), viewer):
        options.append(("requisitions", "JANUS Requisitions and original Core care"))
    if not options:
        await reply(
            interaction,
            "Actual JANUS Core records:\n"
            + (
                "\n".join(x["label"] + ": " + ", ".join(x["tags"]) for x in data["cores"])
                or (
                    "No original Core has been admitted for your current roles."
                    if data["source_available"]
                    else "JANUS Core setup is awaiting rules review."
                )
            ),
        )
        return

    async def choose(current: discord.Interaction, selected: str) -> None:
        if selected == "requisitions":
            from girlframe.discord_adapter.m3_janus_requisitions import open_janus_requisitions

            await open_janus_requisitions(current, JanusRequisitionService(service.game))
            return
        if selected.startswith("mind:"):
            from girlframe.discord_adapter.m3_janus_play import open_brain_link

            await open_brain_link(current, service.game, selected.removeprefix("mind:"))
            return
        if selected == "battery":
            from girlframe.discord_adapter.m3_janus_play import open_battery

            await open_battery(current, service.game)
            return
        await open_core_setup(
            current, service, None if selected == "request" else selected.removeprefix("setup:")
        )

    await Picker(
        viewer.user_id, "JANUS — original Core and actual source work", tuple(options), choose
    ).show(interaction)


async def open_core_withdraw(
    interaction: discord.Interaction, service: JanusService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.withdraw,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
        )
        return "Your pending source setup is withdrawn. No Core resources were created."

    form = NativeForm(
        viewer.user_id,
        "Withdraw pending original Core setup",
        "The next source response belongs to another original participant. "
        "You may withdraw your own pending request/control proposal, including while paused. "
        "This grants no successor character or fictional consent.",
        [
            Field(
                "withdraw",
                "Your own pending source request",
                (("yes", "Withdraw this pending admission"),),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
