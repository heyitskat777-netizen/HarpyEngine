"""Private source-owned trackers and original-human body/scene fact controls."""

import asyncio
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_tracker_implants as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_tracker_implants import TrackerService
from girlframe.services.onboarding import WorkflowError


async def open_tracker(
    interaction: discord.Interaction, service: TrackerService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.menu, viewer, identity)
    if "awards" in data:
        if not data["awards"]:
            await reply(interaction, "A genuine held original Handler advancement is required.")
            return
        fields = [
            Field(
                "award",
                "Actual held advancement",
                tuple((x["id"], x["label"]) for x in data["awards"]),
            )
        ]
        for index, row in enumerate(data["roster"]):
            fields.extend(
                [
                    Field("site_" + str(index), clean(row["label"]) + " — actual body part"),
                    Field(
                        "asset_" + str(index),
                        "Existing physical Girl Asset, if this part has one",
                        (("none", "Site has no existing Asset"),)
                        + tuple((x["id"], clean(x["name"])) for x in row["assets"]),
                    ),
                ]
            )
        fields.extend(
            [
                Field(
                    "actual",
                    "Actual secret physical installation",
                    (("actual", "I actually implant each listed original body"),),
                ),
                Field("account", "Actual installation facts (private)", paragraph=True),
            ]
        )

        async def acquire(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                values["award"][0],
                data["game_revision"],
                tuple(
                    rules.Site(
                        actor=ActorRef.model_validate(row["actor"]),
                        site=values["site_" + str(i)],
                        asset=None
                        if values["asset_" + str(i)] == ("none",)
                        else values["asset_" + str(i)][0],
                    )
                    for i, row in enumerate(data["roster"])
                ),
                values["account"],
                actual=values["actual"] == ("actual",),
            )
            return "Actual original trackers installed privately. Saved controls: " + str(
                result["id"]
            )

        form = NativeForm(
            viewer.user_id,
            "Tracker Implants — actual installation",
            "Choose an actual anatomical site for each original Girl. "
            "Existing Assets are optional site bindings; no new mechanical Assets are created.",
            fields,
            acquire,
            values={"award": (identity,)} if identity else None,
        )
        await reply(interaction, form.text(), form)
        return
    if not data["owner"]:

        async def body_fact(current: discord.Interaction, mode: str) -> None:
            if mode == "moment":
                fields = [
                    Field(
                        "scene",
                        "Actual original scene",
                        tuple((x["id"], x["label"]) for x in data["scenes"]),
                    ),
                    Field(
                        "account",
                        "Your actual private fictional moment (not OOC notes)",
                        paragraph=True,
                    ),
                ]
            elif mode == "void":
                fields = [
                    Field("source_event", "Actual committed body-Void event ID"),
                    Field("asset", "Actual changed Girl Asset ID"),
                    Field("site", "Anatomical part actually affected by that source"),
                ]
            else:
                fields = [
                    Field("tracker", "Actual physically found implant ID"),
                    Field("account", "Actual physical removal", paragraph=True),
                    Field(
                        "actual",
                        "Actual recovery",
                        (("actual", "I actually remove this object from my original body"),),
                    ),
                ]

            async def submit(actual: discord.Interaction, values: dict[str, Any]) -> str:
                human = viewer_from_interaction(actual)
                if mode == "moment":
                    await asyncio.to_thread(
                        service.record_moment,
                        human,
                        str(actual.id),
                        data["game_revision"],
                        int(values["scene"][0]),
                        values["account"],
                    )
                elif mode == "void":
                    await asyncio.to_thread(
                        service.record_site_void,
                        human,
                        str(actual.id),
                        data["game_revision"],
                        values["source_event"],
                        values["asset"],
                        values["site"],
                    )
                else:
                    await asyncio.to_thread(
                        service.remove,
                        human,
                        str(actual.id),
                        data["game_revision"],
                        values["tracker"],
                        ActorRef.model_validate(data["actor"]),
                        values["account"],
                        actual=values["actual"] == ("actual",),
                    )
                return (
                    "Actual original body/source fact saved privately. "
                    "No dialogue, consent or extra roll was generated."
                )

            form = NativeForm(
                viewer.user_id,
                "Actual body / fictional scene fact",
                "Record an actual source event. This form discloses no secret "
                "implant sites or Handler knowledge.",
                fields,
                submit,
            )
            await reply(current, form.text(), form)

        await reply(
            interaction,
            "Record only your actual original body's facts.",
            Picker(
                viewer.user_id,
                "Actual fact",
                (
                    ("moment", "Supply an actual private fictional moment"),
                    ("void", "Attribute an actual body-Void source to its site"),
                    ("remove", "Record actual removal of a physically found implant"),
                ),
                body_fact,
            ),
        )
        return
    lines = ["**Your original tracker knowledge**"]
    for item in data["implants"]:
        lines.append(
            clean(item["site"])
            + " — "
            + (
                "attached; actual cell " + str(item["cell"])
                if item["attached"]
                else "actually removed"
            )
            + (("; " + clean(item["gap"])) if item["gap"] else "")
        )
    for alert in data["alerts"]:
        lines.append("Alert: " + alert["reason"] + "; actual source " + alert["source_event"])

    async def choose(current: discord.Interaction, mode: str) -> None:
        live = {x["id"]: x for x in data["implants"] if x["attached"]}
        if not live:
            raise WorkflowError("No actual attached tracker grants another Play")
        if mode == "presence":
            fields = [
                Field(
                    "tracker",
                    "Original tracked body at your actual initial location",
                    tuple((x["id"], clean(x["site"])) for x in live.values()),
                ),
                Field("account", "Actual presence of your original Handler body", paragraph=True),
            ]
        elif mode == "remove":
            fields = [
                Field(
                    "tracker",
                    "Actual attached hardware",
                    tuple((x["id"], clean(x["site"])) for x in live.values()),
                ),
                Field(
                    "actual",
                    "Actual physical removal",
                    (("actual", "My original Handler body actually removes it in reach"),),
                ),
                Field("account", "Actual removal and recovered object", paragraph=True),
            ]
        else:
            fields = [
                Field(
                    "tracker",
                    "Actual original implanted body",
                    tuple((x["id"], clean(x["site"])) for x in live.values()),
                ),
                Field(
                    "scene",
                    "Actual contact / observation scene",
                    tuple((x["id"], x["label"]) for x in data["scenes"]),
                ),
            ]
            if mode == "tracker_voyeur":
                fields.append(
                    Field(
                        "moment",
                        "Actual original-human fictional moment",
                        tuple(
                            (x["id"], clean(x["label"]) + " / " + str(x["scene"]))
                            for x in data["moments"]
                        ),
                    )
                )

        async def submit(actual: discord.Interaction, values: dict[str, Any]) -> str:
            if mode == "presence":
                await asyncio.to_thread(
                    service.record_initial_presence,
                    viewer_from_interaction(actual),
                    str(actual.id),
                    data["id"],
                    data["game_revision"],
                    values["tracker"][0],
                    values["account"],
                )
                return (
                    "Your previously unknown actual initial presence recorded. No person was moved."
                )
            if mode == "remove":
                await asyncio.to_thread(
                    service.remove,
                    viewer_from_interaction(actual),
                    str(actual.id),
                    data["game_revision"],
                    values["tracker"][0],
                    ActorRef.model_validate(data["handler"]),
                    values["account"],
                    actual=values["actual"] == ("actual",),
                )
                return "Same actual tracker removed; real recovered object and private alert saved."
            result = await asyncio.to_thread(
                service.start_play,
                viewer_from_interaction(actual),
                str(actual.id),
                data["game_revision"],
                values["tracker"][0],
                cast(Literal["tracker_intercept", "tracker_voyeur"], mode),
                int(values["scene"][0]),
                moment=values.get("moment", (None,))[0],
            )
            return (
                "Source-owned Handler Play ready. Open Handler Plays or Requests "
                "to perform it. Reference: " + str(result["id"])
            )

        form = NativeForm(
            viewer.user_id,
            "Tracker — "
            + dict(
                (
                    *rules.PLAYS,
                    ("remove", "Actual removal"),
                    ("presence", "Actual initial presence"),
                )
            )[mode],
            "Interception/observation requires real known co-presence or "
            "completed travel. It does not move a target or fabricate private information.",
            fields,
            submit,
        )
        await reply(current, form.text(), form)

    await reply(
        interaction,
        "\n".join(lines)[:1900],
        Picker(
            viewer.user_id,
            "Tracker source controls",
            (*rules.PLAYS, ("remove", "Actually remove an implanted tracker"))
            + (
                (("presence", "Record your actual initial presence"),)
                if data["can_record_initial"]
                else ()
            ),
            choose,
        ),
    )
