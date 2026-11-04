"""Native Observation orders and individual human consequence requests."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_strain_effects import WAIT
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_observation_state import Details, Kind
from girlframe.services.m3_observation import ObservationService
from girlframe.services.onboarding import WorkflowError

LABELS = {
    "remove_girl_void_asset": "Remove a Girl Void Asset",
    "remove_frame_void_asset": "Remove a Frame Void Asset",
    "assigned_observer": "Assign a Junior Handler or Guard",
    "medical_probing": "Scientists and Doctors examine you",
    "hospital_stay": "An extended hospital stay",
    "public_display_tag": "Public display and a populace Tag",
    "moderate_punishment": "Face Moderate Punishment",
    "reprogram": "Reprogram your starting Identities",
    "become_dog": "Become the Dog",
    "harpy_candidate_tag": "Gain Harpy Candidate",
    "director_or_rival_arrives": "The Director or a rival Handler appears",
}


def one(values: dict[str, Any], key: str) -> str | None:
    return next(iter(values.get(key, ())), None)


async def open_order(
    interaction: discord.Interaction,
    service: ObservationService,
    identity: str,
    *,
    review: bool = False,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.cycle.review, viewer, identity)
    if viewer.user_id != data["handler"]:
        raise WorkflowError("Only the current Handler records its own Observation suspicion.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        hiding = one(values, "hiding")
        if hiding not in ("yes", "no"):
            raise WorkflowError("Record your own explicit hiding-suspicion decision.")
        await asyncio.to_thread(
            service.suspicion if review else service.order,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            int(one(values, "subject") or "0"),
            hiding == "yes",
            values["account"],
        )
        return (
            "Hiding-suspicion review saved."
            if review
            else "Observation order saved. That Girl's next Off-Duty Play uses Void Observation."
        )

    form = NativeForm(
        viewer.user_id,
        "Review attempts to hide Void changes" if review else "Place a Girl under Void Observation",
        "Review before the first consequence selection; saved dice remain intact."
        if review
        else "Record your actual suspicion of Void changes before their Off-Duty Play. "
        "Observation replaces their ordinary roll. Each human makes their own later choices.",
        [
            Field("subject", "Girl under observation", data["participants"]),
            Field(
                "hiding",
                "Do you suspect attempts to hide the changes?",
                (("yes", "Yes"), ("no", "No")),
            ),
            Field("account", "Your actual suspicion", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_work(
    interaction: discord.Interaction, service: ObservationService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] != "pending":
        await reply(interaction, "This Observation decision is already saved.")
        return
    if data["owner_id"] != str(viewer.user_id):
        await reply(
            interaction, "Waiting for this decision's actual owner. Their response remains pending."
        )
        return
    title = "Void Observation — your choices"
    if data.get("response_required"):
        title = "Observation — " + data["npc_name"]
        fields = [
            Field(
                "response",
                "Will you play this actual appearance / assignment?",
                (("yes", "Confirm this NPC action"), ("no", "Return the proposal to the Handler")),
            )
        ]
    elif data["kind"] == "observation_choice":
        fields = [
            Field(
                "choices",
                "Choose your consequences",
                tuple((x, LABELS[x]) for x in data["options"]),
                data["count"],
                data["count"],
            )
        ]
    else:
        kind = data["consequence"]
        title = "Observation — " + LABELS[kind]
        fields = []
        if kind in ("remove_girl_void_asset", "remove_frame_void_asset"):
            fields.append(Field("asset", "Actual Void Asset to remove", data["assets"] or WAIT))
        elif kind in ("assigned_observer", "director_or_rival_arrives"):
            fields.append(Field("npc", "Actual available NPC", data["npcs"] or WAIT))
        elif kind == "public_display_tag":
            fields.append(Field("tag", "Tag given by the populace"))
        elif kind == "reprogram":
            fields.append(
                Field(
                    "identity",
                    "Current Identity to retain",
                    tuple(
                        (x["id"], entity_label(x)) for x in data["identities"] if not x["protected"]
                    ),
                )
            )
            if "Malfunctioning" not in data["starting_identities"]:
                paired_slots = {x["slot"] for x in data["identities"] if x["paired"]}
                fields.append(
                    Field(
                        "slot",
                        "Starting slot to replace",
                        tuple(
                            (x, x)
                            for i, x in enumerate(data["starting_identities"])
                            if i not in paired_slots
                        ),
                    )
                )
        fields.append(Field("account", "Actual consequence / details", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if data.get("response_required"):
            if one(values, "response") not in ("yes", "no"):
                raise WorkflowError("Give your own explicit response for this NPC.")
            await asyncio.to_thread(
                service.answer_npc,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["period_revision"],
                data["game_revision"],
                one(values, "response") == "yes",
            )
            return (
                "Your NPC response is saved. Scene participation still needs its own confirmation."
            )
        if data["kind"] == "observation_choice":
            await asyncio.to_thread(
                service.select,
                viewer_from_interaction(current),
                str(current.id),
                data["period_id"],
                data["period_revision"],
                data["game_revision"],
                int(data["subject_id"]),
                cast(tuple[Kind, ...], tuple(values["choices"])),
            )
            return "Your choices are saved. Reopen requests for each actual consequence."
        result = await asyncio.to_thread(
            service.apply,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["period_revision"],
            data["game_revision"],
            Details(
                account=values["account"],
                asset=one(values, "asset"),
                npc=one(values, "npc"),
                identity=one(values, "identity"),
                slot=one(values, "slot"),
                tag=values.get("tag", ""),
            ),
        )
        if result["awaiting_human"]:
            return "Proposal saved for the actual NPC controller. The consequence remains pending."
        return "Consequence saved. Complete the selected scene and remaining work before recovery."

    form = NativeForm(
        viewer.user_id,
        title,
        "Review your own required decision, then confirm. Other humans' replies stay pending.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
