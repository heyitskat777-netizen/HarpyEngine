"""Private original-role Beneath controls using the shared native confirmation form."""

from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm, threaded
from girlframe.discord_adapter.m2_ui import YES, entities, menu, one, text
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.onboarding import WorkflowError


def choice_fields(decision: dict[str, Any]) -> list[Field]:
    kind, data = decision["kind"], decision["harpy_beneath"]
    if kind == "harpy_beneath_select":
        level = decision["result"]["tier"]
        if level == "mid" and len(data["base"]) < 2:
            # Keep the real source pending for human guidance; no impossible Select
            # or invented Status/Bond can satisfy the printed two-effect result.
            return []
        options = tuple(
            data["base"]
            if level == "mid"
            else data["base"] + data["extra"] + (["damage"] if level == "low" else [])
        )
        count = 1 if level == "low" else 2
        fields = [
            menu(
                "options", "Printed effects (high: one base and one extra)", options, count, count
            ),
            text("text", "Describe the actual action"),
            text("fields.tag", "New Tag, only if giving one", required=False),
            text("fields.locked_tag", "Known Tag ID or new, only if locking", required=False),
        ]
        if data["tags"]:
            fields[-1] = Field(
                "fields.locked_tag",
                "Known Tag to lock (or new Tag)",
                tuple((x["id"], x["label"]) for x in data["tags"])
                + (("new", "The new Tag above"),),
                required=False,
            )
        if data.get("issuers"):
            fields += [
                Field(
                    "fields.issuer",
                    "Actual superior, only if Punishing",
                    tuple((x["token"], x["label"]) for x in data["issuers"]),
                    required=False,
                ),
                text("fields.order", "Exact actual order to this Harpy", required=False),
            ]
        return fields
    if kind == "harpy_beneath_details":
        if "bond" in data["options"]:
            return [
                Field(
                    "fields.bond",
                    "Your actual existing Bond to weaken",
                    tuple((x["token"], x["label"]) for x in data["bonds"]),
                )
            ]
        return [entities("denied", "Your actual owned undamaged Asset", data["assets"], 1, 1)]
    if kind == "harpy_beneath_pin_response":
        return [
            menu("options", "Your actual response", ("narrative", "play")),
            text("text", "Describe your own response", required=False),
        ]
    if kind == "harpy_beneath_order_confirmation":
        return [
            Field("flag", "Did you give this exact real order?", YES),
            text("text", "Your actual issuer account"),
        ]
    raise WorkflowError("Resume the actual required child or Punishment through its owned controls")


async def open_beneath(
    interaction: discord.Interaction,
    game: Any,
    ref: ActorRef,
    *,
    channel: int | None = None,
    parent: dict[str, Any] | None = None,
) -> None:
    service = ActorPlayService(game)
    channel = channel if channel is not None else int(interaction.channel_id or 0)
    data = await threaded(
        lambda: service.preview(viewer_from_interaction(interaction), channel, ref)
    )
    actor = data["actor"]
    targets = [x for x in data["opponents"] if x["ref"]["kind"] == "pilot"]
    if not targets:
        raise WorkflowError("Join an actual original Girl to this Harpy's scene first")
    fields = [
        text("context", "Describe your actual action"),
        Field("target", "Actual original Girl", tuple((x["token"], x["name"]) for x in targets)),
    ]
    identities = [x for x in actor["identities"] if not x["marked"] and not x["paired"]]
    if identities:
        fields.append(
            entities("identity", "Own unmarked Identity (optional)", identities, 0, 1, False)
        )
    fields += [
        menu("gain", "Heat gained if marking", ("1", "2", "3")),
        menu("heat", "Actual own Heat to spend", tuple(str(x) for x in range(actor["heat"] + 4))),
    ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        identity = one(values, "identity")
        target = next(x for x in targets if x["token"] == one(values, "target"))
        result = await threaded(
            lambda: service.begin(
                viewer_from_interaction(current),
                str(current.id),
                channel,
                ref,
                actor["source_sha256"],
                ActorRef.model_validate(data["adjudicator"]["ref"])
                if data["adjudicator"]["ref"]
                else None,
                data["cast_revision"],
                PlayInput(
                    play="put_someone_beneath_you",
                    context=values["context"],
                    target_actor=ActorRef.model_validate(target["ref"]),
                    heat=int(one(values, "heat", "0")),
                    identity=identity,
                    gain=int(one(values, "gain", "0")) if identity else 0,
                    parent=parent["action_id"] if parent else None,
                    trigger_confirmed=True,
                ),
            )
        )
        return f"Beneath saved: {result['action_id']}. Resume your own private choice."

    await NativeForm(
        interaction.user.id,
        "Your actual Harpy — Put Someone Beneath You",
        "Use her actual resources; Harpies have no Foundation Status. "
        "Original affected people choose their own private details.",
        fields,
        submit,
    ).present(interaction)


def choice_description(decision: dict[str, Any]) -> str:
    """The issuing human sees the exact saved order before its own confirmation."""
    data = decision["harpy_beneath"]
    if decision["kind"] == "harpy_beneath_order_confirmation":
        return (
            f"{data['issuer']}: confirm only the order you actually issued to "
            f"{data['recipient']} against {data['target']}.\n\n{data['order']}"
        )
    return (
        "Use the actual original people and resources. Harpies have no Foundation Status. "
        "The affected person chooses their own private Bond or Asset details."
    )
