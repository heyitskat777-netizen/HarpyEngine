"""Private initial-position dropdowns and distinct actual facilitator review."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import CockpitAction, InitialPlacement
from girlframe.services.m3_physical import PhysicalService

MODES = (
    ("outside_frame", "Outside my Frame"),
    ("inside_frame", "Inside its cockpit, not piloting"),
    ("piloting", "Piloting my actual Frame"),
)


async def open_initial(interaction: discord.Interaction, service: PhysicalService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.preview, viewer)
    if data["pending_id"] is not None:
        await open_review(interaction, service, data["pending_id"])
        return
    if data["placement"] is not None and not data["can_record_unknown"]:
        placement = data["placement"]
        if data["frame_locks"]:
            await open_frame(interaction, service, data["frame_locks"][-1])
            return
        text = "**Your recorded physical facts**\nGirl's map cell: " + (
            str(tuple(data["actual_cell"]))
            if data["actual_cell"] is not None
            else "Unknown/offstage"
        )
        text += "\nRecorded occupancy: " + dict(MODES)[placement["mode"]]
        text += "\nRecorded Frame cell: " + (
            str(tuple(placement["frame_cell"]))
            if placement["frame_cell"] is not None
            else "Unknown"
        )
        if data["frame_instance"] != placement["frame_instance"]:
            text += "\nThis record refers to your earlier Frame. "
            text += "Your current Frame's position awaits its own source."
        if placement["incapacitated"] or not placement["vitals_active"] or placement["subsumed"]:
            await reply(interaction, text + "\nActual extraction or medical recovery is required.")
            return
        cockpit_options = []
        if placement["mode"] != "outside_frame":
            cockpit_options.append(("exit", "Leave this cockpit"))
        if placement["occupied_frame_owner"] is None:
            if placement["mode"] != "inside_frame":
                cockpit_options.append(("sit", "Be inside my Frame without piloting"))
            if placement["mode"] != "piloting":
                cockpit_options.append(("pilot", "Pilot my actual assigned Frame"))

        async def operate(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.operate,
                viewer_from_interaction(current),
                str(current.id),
                data["game_revision"],
                CockpitAction(
                    actor=ActorRef.model_validate(data["actor"]),
                    operation=values["operation"][0],
                    expected_position=data["position_sha256"],
                    account=values["account"],
                    confirmed=True,
                ),
            )
            return (
                "Your actual cockpit state is saved. Resolve the resulting Void consequence "
                "in your requests inbox before another Play."
                if result.get("void_works")
                else "Your actual cockpit state is saved."
            )

        form = NativeForm(
            viewer.user_id,
            "Your actual cockpit",
            text,
            [
                Field("operation", "Your physical operation", tuple(cockpit_options)),
                Field("account", "Describe your actual action", paragraph=True),
            ],
            operate,
        )
        await reply(interaction, form.text(), form)
        return
    locations = {x["id"]: x for x in data["locations"]}
    if data["placement"] is not None:
        previous = data["placement"]
        if previous["girl_cell"] is not None:
            locations["__current_girl"] = dict(
                id="__current_girl", name="Actual recorded Girl cell", cell=previous["girl_cell"]
            )
        if (
            previous["frame_instance"] == data["frame_instance"]
            and previous["frame_cell"] is not None
        ):
            locations["__current_frame"] = dict(
                id="__current_frame", name="Actual recorded Frame cell", cell=previous["frame_cell"]
            )
    if not locations:
        await reply(
            interaction, "The actual campaign map needs to be initialized before physical setup."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(current),
            str(current.id),
            data["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=tuple(locations[values["girl_location"][0]]["cell"]),
                frame_cell=tuple(locations[values["frame_location"][0]]["cell"]),
                mode=values["mode"][0],
                account=values["account"],
                facts_confirmed=True,
            ),
        )
        return (
            "Your original physical facts are saved for facilitator review. "
            "Reopen /character requests. Request: " + str(result["id"])
        )

    options = tuple((key, x["name"]) for key, x in locations.items())
    form = NativeForm(
        viewer.user_id,
        "Record original physical facts",
        "Propose your actual current body and Frame positions for facilitator review. "
        "Choose your actual occupancy. While inside, the Girl and Frame share a map cell.",
        [
            Field("girl_location", "Where is your Girl?", options),
            Field("frame_location", "Where is your actual assigned Frame?", options),
            Field(
                "mode",
                "Your actual Frame occupancy",
                ((data["placement"]["mode"], dict(MODES)[data["placement"]["mode"]]),)
                if data["placement"]
                else MODES,
            ),
            Field("account", "Describe the actual physical facts", paragraph=True),
            Field(
                "confirm",
                "Confirm these actual facts for review",
                (("yes", "Save my original factual proposal"),),
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_frame(
    interaction: discord.Interaction,
    service: PhysicalService,
    identity: str,
    target: ActorRef | None = None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.frame, viewer, identity, target)
    if data["can_voice"] and target is None and len(data["occupants"]) > 1:
        from girlframe.discord_adapter.m3_punishments import Picker

        people = {x["token"]: x for x in data["occupants"]}

        async def choose(current: discord.Interaction, token: str) -> None:
            await open_frame(
                current, service, identity, ActorRef.model_validate(people[token]["ref"])
            )

        await Picker(
            viewer.user_id,
            "Choose the actual cockpit occupant",
            tuple((key, x["label"]) for key, x in people.items()),
            choose,
        ).show(interaction)
        return
    text = "**Actual Frame cockpit — " + clean(data["label"]) + "**\n"
    text += "Locked." if data["active"] else "The Frame explicitly opened the cockpit."
    if data["present"]:
        text += (
            "\nThis body's extraction is allowed."
            if data["allowed"] or not data["active"]
            else "\nThis body's extraction needs the Frame's actual consent."
        )
    else:
        text += "\nThe original body is no longer in this cockpit."
    text += "\nOpening or extraction does not restore vital signs or repair Assets."
    operations = []
    if data["can_voice"]:
        if data["present"]:
            operations.extend(
                [
                    ("allow", "As the Frame: allow this body's extraction"),
                    ("refuse", "As the Frame: refuse this body's extraction"),
                ]
            )
        operations.append(("open", "As the Frame: open this cockpit"))
    if data["extractors"]:
        operations.append(("extract", "As my actual present role: extract this body"))
    if not operations:
        await reply(
            interaction, text + "\nWaiting for an actual Frame response or present extractor."
        )
        return
    fields = [Field("operation", "Your actual role's decision", tuple(operations))]
    if data["extractors"]:
        fields.append(
            Field(
                "extractor",
                "Your actual extraction role (extraction only)",
                tuple((x["token"], x["label"]) for x in data["extractors"]),
                minimum=0,
                required=False,
            )
        )
    fields.append(Field("account", "Describe the actual response or extraction", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        subject = ActorRef.model_validate(data["subject"])
        operation = values["operation"][0]
        if operation == "extract":
            selected = values.get("extractor", ())
            known = {x["token"]: x for x in data["extractors"]}
            if len(selected) != 1 or selected[0] not in known:
                from girlframe.services.onboarding import WorkflowError

                raise WorkflowError("Choose the actual present role performing extraction.")
            await asyncio.to_thread(
                service.extract_body,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["expected"],
                data["revision"],
                ActorRef.model_validate(known[selected[0]]["ref"]),
                values["account"],
                target=subject,
            )
            return "The actual body was extracted. Vital signs and injuries remain as recorded."
        await asyncio.to_thread(
            service.respond_frame,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["expected"],
            data["revision"],
            operation,
            values["account"],
            target=subject,
        )
        return "The Frame's explicit response is recorded. No extraction or healing was assumed."

    form = NativeForm(viewer.user_id, "Actual Frame consent and extraction", text, fields, submit)
    await reply(interaction, form.text(), form)


async def open_journey_recovery(
    interaction: discord.Interaction,
    service: PhysicalService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.journey, viewer, identity)
    locations = {x["id"]: x for x in data["locations"]}
    options = [(key, value["name"]) for key, value in locations.items()]
    if data["participant"]["kind"] in ("pilot", "handler"):
        options.insert(0, ("unknown", "Actual recovery; map position still unknown"))
    if not options:
        await reply(
            interaction, "Record the actual map before confirming this world role's recovery."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        location = values["location"][0]
        cell = None if location == "unknown" else tuple(locations[location]["cell"])
        await asyncio.to_thread(
            service.recover_journey,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            ActorRef.model_validate(data["participant"]),
            data["expected"],
            data["revision"],
            cell,
            values["account"],
        )
        return "Your actual role's recovery and location are recorded."

    form = NativeForm(
        viewer.user_id,
        "Recover an interrupted journey",
        "The original trip was interrupted. Record your actual surviving role's "
        "recovery after it happens; no return or elapsed time is assumed.",
        [
            Field("location", "Actual recovery position", tuple(options)),
            Field("account", "Describe the actual recovery", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_review(
    interaction: discord.Interaction, service: PhysicalService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    body, proposal = data["review"], data["review"]["proposal"]
    text = "**Original physical facts: " + clean(body["label"]) + "**\n"
    text += (
        "Girl's cell: "
        + str(tuple(proposal["girl_cell"]))
        + "\nFrame's cell: "
        + str(tuple(proposal["frame_cell"]))
    )
    text += "\nOccupancy: " + dict(MODES)[proposal["mode"]] + "\n" + clean(proposal["account"])
    if data["state"] == "resolved":
        await reply(
            interaction,
            text + "\nReview: " + clean(body["decision"]) + "\n" + clean(body["response"]),
        )
        return
    decisions = (
        (
            ("accept", "Confirm these actual original facts"),
            ("decline", "Decline this factual proposal"),
        )
        if data["can_review"]
        else (("withdraw", "Withdraw my pending proposal"),)
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.decide,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["decision"][0],
            values["account"],
        )
        return "Original physical review saved: " + str(result["decision"]) + "."

    form = NativeForm(
        viewer.user_id,
        "Review actual physical facts",
        text,
        [
            Field("decision", "Your own review action", decisions),
            Field("account", "Your actual response", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
