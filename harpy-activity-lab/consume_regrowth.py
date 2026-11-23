"""Activity controls for the original CONSUME Let Us Partake decision."""

import json

from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.onboarding import WorkflowError

KIND = "consume_partake"


def regrowth_operations(data, field, operation, account):
    girl = field("girl_asset", "Your Girl Asset", data["girl_assets"])
    replacement = field(
        "replace_frame",
        "Frame Asset to replace if at capacity",
        data["frame_replacements"],
        required=False,
    )
    forms = {
        "pass": [account],
        "excrete": [
            girl,
            field("new_name", "New Void Frame Asset"),
            field("new_description", "Asset description"),
            replacement,
            account,
        ],
        "appearance": [girl, field("appearance", "Your new appearance"), account],
    }
    if data["frame_assets"]:
        slots = []
        for index in (1, 2):
            slots += [
                field(
                    f"frame_{index}",
                    f"Frame component {index}",
                    data["frame_assets"],
                    required=index == 1,
                ),
                field(
                    f"replace_{index}",
                    f"Replace for component {index} if required",
                    data["regrow_replacements"],
                    required=False,
                ),
            ]
        forms["regrow"] = [girl, *slots, account]
    return [
        operation(key, label, forms[key])
        | (
            {
                "regrowth": {
                    "missing": data["regrow_missing"],
                    "free": data["regrow_free"],
                }
            }
            if key == "regrow"
            else {}
        )
        for key, label in data["options"]
        if key in forms
    ]


def regrowth_answer(op, values):
    if op not in ("pass", "regrow", "excrete", "appearance"):
        raise WorkflowError("Choose a printed Let Us Partake outcome.")
    fields = {} if op == "pass" else {"girl_asset": values["girl_asset"]}
    if op == "regrow":
        frames, replacements = [], {}
        for index in (1, 2):
            frame = values.get(f"frame_{index}")
            replacement = values.get(f"replace_{index}")
            if replacement and (not frame or replacement in replacements.values()):
                raise WorkflowError(
                    "Pair each replacement with a component and choose distinct replacements."
                )
            if not frame:
                continue
            if frame in frames:
                raise WorkflowError("Choose distinct components to regrow.")
            frames.append(frame)
            if replacement:
                replacements[frame] = replacement
        fields["frame_assets"] = json.dumps(frames)
        if replacements:
            fields["regrow_replacements"] = json.dumps(replacements)
    elif op == "excrete":
        fields["new_asset"] = json.dumps(
            {
                "name": values["new_name"],
                "description": values["new_description"],
                "damaged": False,
                "void": True,
            }
        )
        if values.get("replace_frame"):
            fields["replace_frame"] = values["replace_frame"]
    elif op == "appearance":
        fields["appearance"] = values["appearance"]
    return ChoiceAnswer(options=(op,), fields=fields, text=values["account"])
