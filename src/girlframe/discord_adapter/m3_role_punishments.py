"""The chooser instructs; actual scene humans attest; the named executor carries it out."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import KINDS, Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError


async def open_instruction(
    interaction: discord.Interaction, service: RolePunishmentService, identity: str, selection: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    kind, _, branch = selection.partition(":")
    if not data["chooser"] or kind not in data["kinds"]:
        raise WorkflowError("Only the actual original chooser selects this instruction.")
    own = data["pc_choices"]
    fields: list[Field] = []

    def entities(key: str, label: str, entries: list[dict[str, Any]], count: int = 1) -> Field:
        if len(entries) < count:
            raise WorkflowError(
                "This type lacks actual eligible details; choose another instruction."
            )
        return Field(
            key,
            label,
            tuple((x["id"], x.get("name", x.get("label", x["id"]))) for x in entries),
            minimum=count,
            maximum=count,
        )

    if kind == "sedation":
        count = min(2, len(own["identities"]))
        if count:
            fields.append(
                entities("identities", "Actual Identities to mark", own["identities"], count)
            )
    elif kind in ("beating", "compliance_surgery", "frame_disassembly"):
        family = "frame" if kind == "frame_disassembly" else "girl"
        fields.append(
            entities(
                "asset",
                "Actual affected Asset",
                [
                    x
                    for x in own["assets"]
                    if x["family"] == family and (kind != "beating" or not x["damaged"])
                ]
                + (own.get("body_parts", []) if kind == "beating" else []),
            )
        )
        if kind == "compliance_surgery":
            fields += [
                Field("replacement_name", "Replacement Girl Asset name"),
                Field("replacement_description", "Describe the replacement", paragraph=True),
            ]
    elif kind == "revoked_privileges":
        fields += [
            entities("requisition", "Actual held Requisition", own["requisitions"]),
            Field("restoration", "Actual temporary restoration condition", paragraph=True),
        ]
    elif kind == "strict_regulations":
        fields += [
            Field("regulation", "Actual behavioural rule", paragraph=True),
            Field(
                "disclosed",
                "Inform the affected Girl?",
                (("yes", "Inform her"), ("no", "Keep the rule concealed")),
            ),
        ]
    elif kind == "correctional_programming":
        if branch not in ("erase", "embrace"):

            async def choose(current: discord.Interaction, value: str) -> None:
                await open_instruction(current, service, identity, kind + ":" + value)

            await Picker(
                viewer.user_id,
                "Choose the exact correction instruction",
                (("erase", "Erase an Identity"), ("embrace", "Force a Tag embraced")),
                choose,
            ).show(interaction)
            return
        if branch == "embrace":
            fields.append(entities("embrace_tag", "Actual Tag to embrace", own["tags"]))
        if branch == "erase" or own["identity_cap_reached"]:
            fields.append(
                entities(
                    "identities", "Actual ordinary Identity to remove", own["removable_identities"]
                )
            )
    elif kind == "reduced_socialization":
        if own is not None:
            if not own["bonds"]:
                raise WorkflowError("No actual eligible current Bond is available.")
            fields.append(Field("bond_with", "Actual Bond to weaken", tuple(own["bonds"])))
        else:
            fields.append(
                Field(
                    "counterpart",
                    "Actual Bond counterpart",
                    tuple((x["token"], x["label"]) for x in data["peers"]),
                )
            )
    if kind in ("quality_time", "beating"):
        fields.append(Field("tag", "Actual inflicted Tag"))
    fields.append(
        Field(
            "confirm",
            "Your instruction; effects wait for actual execution",
            (("yes", "Instruct these exact details"),),
        )
    )

    async def save(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected: dict[str, Any] = dict(kind=kind)
        counterpart = None
        for field in fields:
            if field.key == "confirm":
                continue
            value = values[field.key]
            if field.key == "counterpart":
                counterpart = ActorRef.model_validate(
                    next(x["ref"] for x in data["peers"] if x["token"] == value[0])
                )
                continue
            if field.key != "identities" and isinstance(value, tuple):
                value = value[0]
            if field.key == "bond_with":
                value = int(value)
            if field.key == "disclosed":
                value = value == "yes"
            if field.key == "asset" and isinstance(value, str) and value.startswith("part:"):
                selected["body_part"] = value.removeprefix("part:")
            else:
                selected[field.key] = value
        instruction = Instruction(
            kind=kind, details_json=Details(**selected).model_dump_json(), counterpart=counterpart
        )
        await asyncio.to_thread(
            service.change,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            instruction=instruction,
        )
        return "Instruction saved. The original executor still owes the actual scene and effect."

    form = NativeForm(
        viewer.user_id,
        "Instruct " + KINDS[kind][0],
        "You choose the type and unspecified details. This records your instruction; "
        "the named actual executor carries it out and receives actual "
        "executor Bonds/Tag attribution.",
        fields,
        save,
    )
    await reply(interaction, form.text(), form)


async def open_role_punishment(
    interaction: discord.Interaction, service: RolePunishmentService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    case = data["case"]
    if case.get("ended_event"):
        await reply(
            interaction,
            "The original source participant ended before this Punishment was performed. "
            "The actual ending is recorded; no Punishment effect or completion was invented.",
        )
        return
    if case["completion_event"]:
        await reply(
            interaction,
            "The exact instructed Punishment and required effects are completed. "
            "Original chooser and executor remain in its source history.",
        )
        return
    if data["stale"]:
        await reply(
            interaction,
            "Recover the original participants and actual source context "
            "before this case continues.",
        )
        return
    if data["chooser"] and case["instruction"] is None:

        async def choose(current: discord.Interaction, value: str) -> None:
            await open_instruction(current, service, identity, value)

        await Picker(
            viewer.user_id,
            "Choose the exact instruction; the executor carries it out",
            tuple((x, KINDS[x][0]) for x in data["kinds"]),
            choose,
        ).show(interaction)
        return
    if data["can_approve"]:
        fields = [
            Field(
                "confirm",
                "Exact proposed details and original executor",
                (("yes", "Approve this exact Moderate proposal"),),
            )
        ]
        operation = dict(approve=True)
        instructions = (
            "Review the exact proposal: " + str(case["instruction"]) + ". "
            "This supplies your own Handler consultation only."
        )
    elif data["executor"] and not case["scene_account"] and case["instruction"]:
        fields = [Field("scene", "Describe the actual on-screen Punishment scene", paragraph=True)]
        operation = {}
        instructions = (
            "Record the actual scene in which you carry out the saved instruction. "
            + (
                "Your original role is also the subject of this source self-Punishment. "
                if case["executor_controller"] == case["subject_controller"]
                else "The other human records attendance. "
            )
            + "Scene descriptions are shared with participants."
        )
    elif data["can_attest"] and case["scene_account"]:
        fields = [
            Field(
                "confirm",
                "Your own actual on-screen attendance",
                (("yes", "I played my actual role in this scene"),),
            )
        ]
        operation = dict(attest=True)
        instructions = case["scene_account"] + "\nConfirm only your own actual attendance."
    elif (
        data["executor"]
        and set(case["attendance"]) == {case["executor_controller"], case["subject_controller"]}
        and not case["effect_event"]
    ):
        fields = [
            Field(
                "account", "Describe your actual execution of the exact instruction", paragraph=True
            ),
            Field(
                "confirm",
                "Actual effect uses the named executor",
                (("yes", "Carry out the exact saved instruction"),),
            ),
        ]
        operation = dict(execute=True)
        instructions = (
            "Actual instruction: " + str(case["instruction"]) + ". "
            "This applies the real sheet/Bond/Tag consequence with your executor identity."
        )
    else:
        await reply(
            interaction,
            "This source case awaits the actual chooser, other participant, "
            "Handler consultation or required consequence. Reopen its actual owned step.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.change,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            **(dict(scene=values["scene"]) if "scene" in values else operation),
            account=values.get("account", ""),
        )
        return "Your contribution is saved. Reopen the case for its next owned step."

    form = NativeForm(
        viewer.user_id, "Actual instruction and execution", instructions, fields, submit
    )
    await reply(interaction, form.text(), form)
