"""Native, resumable basic Handler Plays and source-limited final counters."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import BASIC, Effect, Play
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


async def open_handler_plays(interaction: discord.Interaction, service: HandlerPlayService) -> None:
    data = await asyncio.to_thread(service.options, viewer_from_interaction(interaction))
    targets = {ActorRef.model_validate(x["ref"]).token: x for x in data["targets"]}
    options = [
        ("new", "Make a basic Handler Play"),
        ("off_duty", "Go Off-Duty / actual period and scenes"),
    ]
    options.extend((x["id"], "Resume saved Handler Play") for x in data["tasks"])

    async def choose(current: discord.Interaction, identity: str) -> None:
        if identity == "off_duty":
            from girlframe.discord_adapter.m3_off_duty import open_period
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService

            await open_period(current, OffDutyService(MissionService(service.store)))
        elif identity != "new":
            await open_play(current, service, identity)
        else:

            async def submit(actual: discord.Interaction, values: dict[str, Any]) -> str:
                result = await asyncio.to_thread(
                    service.start,
                    viewer_from_interaction(actual),
                    str(actual.id),
                    data["game_revision"],
                    tuple(ActorRef.model_validate(targets[x]["ref"]) for x in values["targets"]),
                )
                return (
                    "Owned Handler Play saved. Reopen your Inbox or Handler Plays to "
                    "choose its actual effect. Reference: " + str(result["id"])
                )

            if not targets:
                raise WorkflowError(
                    "Create an actual active Cadre before making a basic Handler Play."
                )
            form = NativeForm(
                viewer_from_interaction(current).user_id,
                "Handler Play — affected characters",
                "Choose the actual originals affected. No player reply or consent is generated.",
                [
                    Field(
                        "targets",
                        "Who is affected?",
                        tuple((key, x["label"]) for key, x in targets.items()),
                        maximum=len(targets),
                    )
                ],
                submit,
            )
            await reply(current, form.text(), form)

    await reply(
        interaction,
        "**Handler Plays**\nOrdinary moves use your actual GM appointment; saved "
        "counter moves belong only to their original human chooser.",
        Picker(
            viewer_from_interaction(interaction).user_id, "Handler Plays", tuple(options), choose
        ),
    )


async def open_play(
    interaction: discord.Interaction, service: HandlerPlayService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    grant = data["grant"]
    if data.get("stale") and grant["source"] == "ordinary" and grant["state"] == "pending":

        async def withdraw(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.withdraw,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["game_revision"],
            )
            return (
                "Untouched ordinary move withdrawn. Start a fresh move for the "
                "current body context."
            )

        form = NativeForm(
            viewer_from_interaction(interaction).user_id,
            "Original move needs review",
            data["stale"],
            [
                Field(
                    "confirm",
                    "Withdraw this untouched move?",
                    (("withdraw", "Withdraw without applying an effect"),),
                )
            ],
            withdraw,
        )
        await reply(interaction, form.text(), form)
        return
    if grant["state"] != "pending":
        if grant["state"] == "awaiting_effect":
            await reply(
                interaction,
                "This Handler Play is waiting for its actual effect and owned "
                "followups. Continue its Punishment, body consequence or required work "
                "in your Inbox.",
            )
        else:
            await reply(interaction, "This original Handler Play is complete.")
        return

    async def choose(current: discord.Interaction, play: str) -> None:
        if play == "decline":

            async def decline(actual: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.decline,
                    viewer_from_interaction(actual),
                    str(actual.id),
                    identity,
                    data["game_revision"],
                )
                return (
                    "Your optional counter was explicitly declined. The original "
                    "source and actual death remain recorded."
                )

            form = NativeForm(
                viewer_from_interaction(current).user_id,
                "Decline your optional counter",
                "This records only your own decision not to make the optional "
                "Handler Play; it does not reverse the actual source consequence.",
                [
                    Field(
                        "confirm",
                        "Your actual choice",
                        (("decline", "Decline this optional counter"),),
                    )
                ],
                decline,
            )
            await reply(current, form.text(), form)
            return
        if play == "off_duty":
            if data.get("off_duty"):

                async def link(actual: discord.Interaction, values: dict[str, Any]) -> str:
                    await asyncio.to_thread(
                        service.submit,
                        viewer_from_interaction(actual),
                        str(actual.id),
                        identity,
                        data["game_revision"],
                        "off_duty",
                        Effect(
                            kind="off_duty", account=values["account"], off_duty=data["off_duty"]
                        ),
                    )
                    return (
                        "Actual Off-Duty period linked. This Play completes after "
                        "its real scene and final performance review."
                    )

                form = NativeForm(
                    viewer_from_interaction(current).user_id,
                    "Handler Go Off-Duty",
                    "Use the actual current Cadre period; scenes and participant "
                    "choices stay in the normal Off-Duty workflow.",
                    [Field("account", "Your actual Off-Duty scene intent", paragraph=True)],
                    link,
                )
                await reply(current, form.text(), form)
            else:
                if grant["source"] == "battle_counter":
                    raise WorkflowError(
                        "No eligible real Cadre Off-Duty period exists for this "
                        "counter. Choose another eligible Play or decline it."
                    )
                from girlframe.discord_adapter.m3_off_duty import open_period
                from girlframe.services.m3_missions import MissionService
                from girlframe.services.m3_off_duty import OffDutyService

                await open_period(current, OffDutyService(MissionService(service.store)))
            return
        if play == "mess":

            async def mess(actual: discord.Interaction, kind: str) -> None:
                await effect_form(actual, service, data, cast(Play, play), kind)

            await reply(
                current,
                "Choose the real mechanical effect.",
                Picker(
                    viewer_from_interaction(current).user_id,
                    "Choose a real effect",
                    (
                        ("status", "Raise or lower actual Status"),
                        ("tag", "Give an actual Tag"),
                        ("damage", "Damage an actual Asset"),
                    ),
                    mess,
                ),
            )
            return
        await effect_form(current, service, data, cast(Play, play), play)

    await reply(
        interaction,
        "**Your owned Handler Play**\nThe effect is against the saved original "
        "target(s). A source counter grants one Play without changing who is the "
        "campaign GM.",
        Picker(
            viewer_from_interaction(interaction).user_id,
            "Your Handler Play",
            BASIC
            + (
                (("decline", "Decline this optional counter"),)
                if grant["source"] == "battle_counter"
                else ()
            ),
            choose,
        ),
    )


async def effect_form(
    interaction: discord.Interaction,
    service: HandlerPlayService,
    data: dict[str, Any],
    play: Play,
    kind: str,
) -> None:
    targets = {x["token"]: x for x in data["targets"]}
    fields = [Field("account", "Information / consequence to communicate", paragraph=True)]
    if kind in ("status", "tag", "damage", "punish"):
        fields.insert(
            0,
            Field(
                "target",
                "Actual affected original",
                tuple((token, x["label"]) for token, x in targets.items()),
            ),
        )
    if kind == "status":
        fields.append(
            Field(
                "status",
                "Status change",
                (("1", "Raise one position"), ("-1", "Lower one position")),
            )
        )
    elif kind == "tag":
        fields.append(Field("tag", "New Tag"))
    elif kind == "damage":
        fields.append(
            Field(
                "asset",
                "Actual undamaged Asset",
                tuple(
                    (target + ":" + asset["id"], x["label"] + " — " + asset["name"])
                    for target, x in targets.items()
                    for asset in x["assets"]
                )
                + tuple(
                    (target + ":substitute", x["label"] + " — printed damage replacement")
                    for target, x in targets.items()
                    if x["ref"]["kind"] in ("handler", "npc")
                ),
            )
        )
    elif kind in ("escalate", "expectation"):
        fields.extend(
            [
                Field("detail", "Actual threat or expectation", paragraph=True),
                Field("stakes", "Stakes or disobedience consequence", paragraph=True),
            ]
        )
    elif kind == "support":
        fields.extend(
            [
                Field("name", "Employee name"),
                Field(
                    "department",
                    "Their support work",
                    (
                        ("base_personnel", "Logistics / catering / base work"),
                        ("mechanic", "Engineering / repair"),
                        ("intelligence_agent", "Information / satellite"),
                        ("public_relations", "Marketing"),
                        ("guard", "Discipline"),
                    ),
                ),
                Field("location", "Actual location", tuple(data.get("locations", ()))),
                Field("detail", "Employee's actual description", paragraph=True),
            ]
        )
    elif kind == "punish":
        fields.append(
            Field(
                "executor",
                "Actual person who will inflict it",
                tuple((x["token"], x["label"]) for x in data.get("executors", [])),
            )
        )

    if kind == "damage":
        fields.append(
            Field(
                "opponent",
                "Actual foe, if outside a Frame",
                (("none", "No separate foe stated"),)
                + tuple((x["token"], x["label"]) for x in data.get("executors", [])),
            )
        )
    if data.get("source_labels"):
        fields.append(
            Field(
                "source_label",
                "Optional playbook narrative context",
                (("none", "No playbook narrative context"),) + tuple(data["source_labels"]),
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        effect_data: dict[str, Any] = dict(kind=kind, account=values["account"])
        if values.get("source_label", ("none",))[0] != "none":
            effect_data["source_label"] = values["source_label"][0]
        selected = values.get("target", (None,))[0]
        if selected is not None:
            effect_data["target"] = ActorRef.model_validate(targets[selected]["ref"])
        if kind == "status":
            effect_data["status"] = int(values["status"][0])
        elif kind == "tag":
            effect_data["tag"] = values["tag"]
        elif kind == "damage":
            if values.get("opponent", ("none",))[0] != "none":
                foe = next(x for x in data["executors"] if x["token"] == values["opponent"][0])
                effect_data["opponent"] = ActorRef.model_validate(foe["ref"])
            token, asset = values["asset"][0].split(":", 1)
            if token != selected:
                raise WorkflowError("Choose an Asset belonging to the actual selected target.")
            effect_data["asset"] = (
                None
                if asset == "substitute" and targets[selected]["ref"]["kind"] in ("handler", "npc")
                else asset
            )
        elif kind in ("escalate", "expectation"):
            effect_data.update(detail=values["detail"], stakes=values["stakes"])
        elif kind == "support":
            location = next(x for x in data["location_records"] if x["id"] == values["location"][0])
            effect_data["npc"] = Npc(
                id="support-" + str(current.id),
                name=values["name"],
                jobs=(values["department"][0],),
                detail=values["detail"],
                controller=viewer_from_interaction(current).user_id,
                cell=tuple(location["cell"]),
                revealed=True,
                employment="foundation",
            )
        elif kind == "punish":
            executor = next(x for x in data["executors"] if x["token"] == values["executor"][0])
            effect_data["executor"] = ActorRef.model_validate(executor["ref"])
        result = await asyncio.to_thread(
            service.submit,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["game_revision"],
            play,
            Effect(**effect_data),
        )
        return "Actual Handler Play saved. " + (
            "Complete its owned effect/followups in your Inbox."
            if result["state"] != "complete"
            else "The real effect is complete."
        )

    if any(
        field.options == () and field.key in ("asset", "executor", "location") for field in fields
    ):
        raise WorkflowError(
            "This effect has no eligible actual resource/person/location. Choose "
            "another effect or establish the missing source first."
        )
    form = NativeForm(
        viewer_from_interaction(interaction).user_id,
        "Handler Play — " + dict(BASIC)[play],
        "Describe and apply the actual effect. Narrative facts do not silently change "
        "Identities, resources, consent or printed abilities.",
        fields,
        submit,
        values={"source_label": ("none",), "opponent": ("none",)},
    )
    await reply(interaction, form.text(), form)


async def open_notice(
    interaction: discord.Interaction, service: HandlerPlayService, identity: str
) -> None:
    from girlframe.discord_adapter.ledger import clean

    data = await asyncio.to_thread(service.notice, viewer_from_interaction(interaction), identity)
    lines = [
        "**Actual Handler Play — " + clean(str(data["play"])) + "**",
        "Effect complete."
        if data["state"] == "complete"
        else "Actual source committed; owned consequences remain pending.",
        clean(data["account"]),
    ]
    for key in ("detail", "stakes", "tag"):
        if data[key]:
            lines.append(clean(str(data[key])))
    if data["employee"]:
        lines.append(clean(data["employee"]["name"]))
    await reply(interaction, "\n\n".join(lines)[:1950])
