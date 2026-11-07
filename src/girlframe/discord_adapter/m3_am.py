"""Owned original AM discovery, Limiter and source secrecy controls."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_am as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_am_scrutinized import ScrutinyService
from girlframe.services.onboarding import WorkflowError

LABELS = {
    "blackmail": "Find blackmail and write its actual Tag",
    "secret": "Beg them to keep the secret; deepen your Bond",
    "unbelieved": "Their factual lower Status makes them unbelievable for now",
    "violence": "Kill this actual NPC where they stand",
    "refuge": "Take refuge with the actual co-present Handler",
}


async def open_am(
    interaction: discord.Interaction, service: ScrutinyService, *, channel: int | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = channel if channel is not None else int(interaction.channel_id or 0)
    from girlframe.services.m3_am_jailbroken import JailbrokenService

    mobility = JailbrokenService(service.game)
    try:
        data = await asyncio.to_thread(service.menu, viewer, channel)
    except (ValueError, WorkflowError) as discovery_error:
        try:
            await asyncio.to_thread(mobility.view, viewer)
        except (ValueError, WorkflowError):
            raise discovery_error from None
        from girlframe.discord_adapter.m3_am_jailbroken import open_jailbroken

        await open_jailbroken(interaction, mobility)
        return
    options = [("propose", "Establish an actual new discovery")] if data["targets"] else []
    from girlframe.services.m3_am_code import CodeService

    try:
        code = await asyncio.to_thread(CodeService(service.game).menu, viewer, channel)
        if code["known"] or code["sessions"] or code.get("operators"):
            options.append(("code", "Actual circuit maintenance"))
    except (ValueError, WorkflowError):
        pass
    try:
        await asyncio.to_thread(mobility.view, viewer)
        options.append(("jailbroken", "Your self-directed body occupancy"))
    except (ValueError, WorkflowError):
        pass
    if data["native"]:
        options.append(("presentation", "Your actual expression and presentation"))
    for value in data["discoveries"]:
        if value["phase"] == "reset_pending" and value["handler_controller"] == viewer.user_id:
            options.append(("reset:" + value["id"], "Take the actual factory-reset NPC"))
        if value["phase"] == "proposed" and value["controller"] == viewer.user_id:
            options.append(("confirm:" + value["id"], "Factual new discovery: " + value["label"]))
        if value["needs_evidence"] and value["handler_controller"] == viewer.user_id:
            options.append(("evidence:" + value["id"], "Handler: review actual new evidence"))
        if value["secret"] and value["controller"] == viewer.user_id:
            options.append(("order:" + value["id"], "Original NPC: issue a source-secret Order"))
        if (
            value["can_report"]
            and value["phase"] == "complete"
            and value["controller"] == viewer.user_id
        ):
            options.append(("report:" + value["id"], "Original discoverer: report the adjustment"))
        if (
            value["report_work"]
            and value["phase"] == "complete"
            and value["controller"] == viewer.user_id
        ):
            options.append(("limiter:" + value["id"], "Install the actual report's Limiter"))
    choices = await asyncio.to_thread(service.game.choices, viewer)
    options += [
        ("choice:" + x["id"], "Continue " + x["kind"].replace("_", " "))
        for x in choices
        if x["kind"].startswith("am_")
    ]
    if not options:
        await reply(
            interaction,
            "No current supported original AM source task. "
            "Use your actual source controls or establish a supported source.",
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        action = values["action"][0]
        if action == "jailbroken":
            from girlframe.discord_adapter.m3_am_jailbroken import open_jailbroken

            await open_jailbroken(current, mobility)
            return None
        if action == "code":
            from girlframe.discord_adapter.m3_am_code import open_code

            await open_code(current, CodeService(service.game), channel=channel)
            return None
        if action.startswith("choice:"):
            await open_choice(current, service.game, action.removeprefix("choice:"))
            return None
        operation, _, identity = action.partition(":")
        value = next((x for x in data["discoveries"] if x["id"] == identity), None)
        if operation == "reset":
            from girlframe.discord_adapter.m3_am_reset import open_reset
            from girlframe.services.m3_am_reset import FactoryResetService

            await open_reset(current, FactoryResetService(service.game), identity)
            return None
        if operation == "limiter":
            await open_report_limiter(current, service, identity)
            return None
        if operation == "propose":
            fields = [
                Field(
                    "target",
                    "Actual new NPC discoverer",
                    tuple(
                        (ActorRef.model_validate(x["ref"]).token, x["label"])
                        for x in data["targets"]
                    ),
                ),
                Field("account", "Describe the actual new realization", paragraph=True),
            ]
        elif operation == "confirm":
            fields = [
                Field(
                    "realized",
                    "Did this original NPC actually newly realize it?",
                    (("yes", "Yes"), ("no", "No")),
                ),
                Field(
                    "lower",
                    "Actual Handler factual rank review",
                    (("yes", "NPC has lower Status"), ("no", "Not established as lower")),
                ),
                Field(
                    "human",
                    "Actual NPC body",
                    (("yes", "A human being"), ("no", "Established nonhuman machine")),
                ),
                Field("account", "Your own actual discovery and factual review", paragraph=True),
            ]
        elif operation == "presentation":
            fields = [
                Field("expression", "Your actual expression"),
                Field("voice", "Your actual own voice"),
                Field("pretend", "Present as a Girl?", (("yes", "Yes"), ("no", "No"))),
            ]
        else:
            fields = [
                Field(
                    "account",
                    "Actual direct order"
                    if operation == "order"
                    else "Actual new evidence"
                    if operation == "evidence"
                    else "Actual report",
                    paragraph=True,
                )
            ]

        async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str:
            owner = viewer_from_interaction(response)
            if operation == "propose":
                selected = next(
                    x
                    for x in data["targets"]
                    if ActorRef.model_validate(x["ref"]).token == answer["target"][0]
                )
                result = await asyncio.to_thread(
                    service.propose,
                    owner,
                    str(response.id),
                    channel,
                    ActorRef.model_validate(selected["ref"]),
                    data["revision"],
                    answer["account"],
                )
                return (
                    "Actual discovery request saved; the original NPC controller "
                    "answers in /campaign am. " + str(result["id"])
                )
            if operation == "confirm":
                await asyncio.to_thread(
                    service.confirm,
                    owner,
                    str(response.id),
                    identity,
                    data["revision"],
                    answer["realized"][0] == "yes",
                    answer["lower"][0] == "yes",
                    answer["human"][0] == "yes",
                    answer["account"],
                )
                return (
                    "Your factual answer is saved. Confirmed discovery holds the scene "
                    "for the AM's real preparation and roll."
                )
            if operation == "presentation":
                await asyncio.to_thread(
                    service.present,
                    owner,
                    str(response.id),
                    data["revision"],
                    answer["expression"],
                    answer["pretend"][0] == "yes",
                    answer["voice"],
                )
                return "Your actual own presentation is saved; live Limiter restrictions remain."
            if operation == "order":
                await asyncio.to_thread(
                    service.secret_order,
                    owner,
                    str(response.id),
                    identity,
                    channel,
                    data["revision"],
                    answer["account"],
                )
                return (
                    "The actual original NPC's source Order is saved; "
                    "the recipient owns its response."
                )
            if operation == "evidence":
                await asyncio.to_thread(
                    service.evidence,
                    owner,
                    str(response.id),
                    identity,
                    data["revision"],
                    answer["account"],
                )
                return "Actual new evidence recorded; the original discoverer may now report."
            await asyncio.to_thread(
                service.report,
                owner,
                str(response.id),
                identity,
                data["revision"],
                answer["account"],
            )
            return "Actual report saved. The original discoverer must install the real Limiter."

        form = NativeForm(
            current.user.id,
            "AM: " + operation,
            "Only actual original bodies, new knowledge and owned factual answers count. "
            + (value["proposal"] if value and operation == "confirm" else ""),
            fields,
            submit,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "AM source controls",
        f"Original scene <#{channel}>. Jailbroken freedoms and actual discoveries; "
        "mind/vessel ownership and terminal reset remain outside this supported source scope.",
        [Field("action", "Current original-source task", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)


async def open_source(
    interaction: discord.Interaction, service: ScrutinyService, identity: str
) -> None:
    channel = await asyncio.to_thread(
        service.source_channel, viewer_from_interaction(interaction), identity
    )
    await open_am(interaction, service, channel=channel)


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    if data["kind"] in ("am_pilot_damage", "am_pilot_response", "am_pilot_damage_wait"):
        from girlframe.discord_adapter.m3_am_code import open_choice as open_code_choice

        await open_code_choice(interaction, game, identity)
        return
    if data.get("am_code") is not None:
        from girlframe.discord_adapter.m3_am_code import open_choice as open_code_choice

        await open_code_choice(interaction, game, identity)
        return
    detail = data["am_scrutinized"]
    if data["kind"] == "am_prepare":
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, game, parent=data)
        return
    if data["kind"] == "am_factory_reset":
        from girlframe.discord_adapter.m3_am_reset import open_reset
        from girlframe.services.m3_am_reset import FactoryResetService

        await open_reset(interaction, FactoryResetService(game), detail["discovery"])
        return
    if data["kind"] == "am_handler":
        from girlframe.discord_adapter.m3_handler_plays import open_play as open_handler
        from girlframe.services.m3_handler_plays import HandlerPlayService

        await open_handler(interaction, HandlerPlayService(game.store), detail["handler_grant"])
        return
    if data["kind"] == "am_limiter":
        fields = [
            Field(
                "identity",
                "Actual ordinary slot to limit",
                tuple(
                    (x["id"], x["name"] + " → " + rules.DEFAULTS[x["slot"]])
                    for x in detail["identities"]
                ),
            ),
            Field(
                "freedom",
                "Actual remaining Jailbroken benefit",
                tuple((x["id"], x["label"]) for x in detail["freedoms"]),
            ),
            Field("account", "Actual installation by the discoverer", paragraph=True),
        ]
    else:
        count = 2 if data["kind"] == "am_handler_options" else 1
        fields = [
            Field(
                "options",
                "Handler: choose two" if count == 2 else "Choose one actual outcome",
                tuple(
                    (
                        x,
                        "Damage an operator Asset; ask how she plays now"
                        if x == "violence" and detail.get("pilot_operator")
                        else LABELS[x],
                    )
                    for x in detail["options"]
                ),
                minimum=count,
                maximum=count,
            )
        ]
        if count == 1:
            fields.append(Field("account", "Actual Tag (max120) or actual action", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if data["kind"] == "am_limiter":
            answer = ChoiceAnswer(
                options=(values["identity"][0],),
                fields={"freedom": values["freedom"][0]},
                text=values["account"],
            )
        else:
            answer = ChoiceAnswer(options=tuple(values["options"]), text=values.get("account", ""))
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return (
            "Your actual source response is saved. Mandatory effects "
            "and the real Handler response remain required."
        )

    form = NativeForm(
        viewer.user_id,
        "AM: " + data["kind"].replace("am_", ""),
        "The actual original role owns this answer. " + detail.get("discoverer", ""),
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_report_limiter(
    interaction: discord.Interaction, service: ScrutinyService, identity: str
) -> None:
    data = await asyncio.to_thread(
        service.limiter_view, viewer_from_interaction(interaction), identity
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        result = await asyncio.to_thread(
            service.resolve_limiter,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["identity"][0],
            cast(rules.Freedom, values["freedom"][0]),
            values["account"],
        )
        if result.get("reset"):
            from girlframe.discord_adapter.m3_am_reset import open_reset
            from girlframe.services.m3_am_reset import FactoryResetService

            await open_reset(current, FactoryResetService(service.game), identity)
            return None
        return (
            "The actual original Limiter is installed "
            "and this report's required effect is complete."
        )

    form = NativeForm(
        interaction.user.id,
        "Actual report: install Limiter",
        "A real report requires one "
        "actual protected default-slot Identity. A fourth Limiter requires the real NPC reset.",
        [
            Field(
                "identity",
                "Actual Identity",
                tuple((x["id"], x["name"]) for x in data["identities"]),
            ),
            Field(
                "freedom",
                "Remaining benefit",
                tuple((x["id"], x["label"]) for x in data["freedoms"]),
            ),
            Field("account", "Actual installation", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
