"""Use HarpyEngine's paid Snoop targets and private original responses."""

from rulebook_text import SNOOP_QUESTION_TEXT as LABELS

from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m3_enforcer_snoop import preview

SNOOP = "snoop"
CHOICES = frozenset(
    {
        "snoop_select",
        "snoop_answer",
        "snoop_object_fact",
        "snoop_relevance",
        "snoop_capacity",
        "snoop_body_context",
    }
)


def snoop_targets(game, viewer, channel):
    available = preview(game, viewer, channel)
    return available["targets"] if available["available"] else []


def snoop_form(data, field, choices, yes_no):
    detail, kind = data["snoop"], data["kind"]
    if kind == "snoop_select":
        return "Choose Snoop questions", [
            field(
                "questions",
                "Printed questions",
                [
                    (value, LABELS.get(value, label))
                    for value, label in choices(detail["questions"])
                ],
                multiple=detail["maximum"] > 1,
            )
        ]
    if kind == "snoop_answer":
        fields = [field("account", "Your original private finding")]
        if detail["question"] in ("valuable", "personal"):
            property_choices = [("ordinary", "Describe an existing ordinary object")] + [
                ("item:" + row["id"], row["label"]) for row in detail["items"]
            ]
            if detail["question"] == "personal":
                property_choices += [
                    ("asset:" + row["id"], row["label"]) for row in detail["assets"]
                ]
            fields.extend(
                [
                    field("object", "Identify actual property", property_choices),
                    field("name", "Ordinary object name", required=False),
                    field(
                        "description",
                        "Ordinary object details and original location",
                        required=False,
                    ),
                ]
            )
        return LABELS[detail["question"]], fields
    if kind == "snoop_capacity":
        return "Review inventory capacity", [
            field(
                "replace",
                "Replace an ordinary Asset only if at cap",
                [("none", "No replacement"), *choices(detail["replacements"])],
            )
        ]
    if kind == "snoop_relevance":
        fields = [field("account", "Actual remaining property")]
        if detail["assets"]:
            fields.append(
                field(
                    "assets",
                    "Relevant Assets",
                    choices(detail["assets"]),
                    multiple=True,
                    required=False,
                )
            )
        return "Review actual property", fields
    return "Confirm source facts", [
        field(
            "confirmed",
            "Inside an actual Frame?"
            if kind == "snoop_body_context"
            else "Does the ordinary object exist and is it accessible?",
            yes_no,
        ),
        field("account", "Actual source facts"),
    ]


def snoop_answer(operation, values):
    if operation == "snoop_select":
        raw = values["questions"]
        return ChoiceAnswer(options=(raw,) if isinstance(raw, str) else tuple(raw))
    if operation == "snoop_answer":
        target = values.get("object")
        if target == "ordinary":
            details = {"name": values["name"], "description": values["description"]}
        elif target:
            kind, identity = target.split(":", 1)
            details = {kind: identity}
        else:
            details = {}
        return ChoiceAnswer(text=values["account"], fields=details)
    if operation == "snoop_relevance":
        return ChoiceAnswer(options=tuple(values.get("assets", ())), text=values["account"])
    if operation == "snoop_capacity":
        value = values["replace"]
        return ChoiceAnswer(fields={} if value == "none" else {"replace": value})
    if operation in ("snoop_object_fact", "snoop_body_context") and values["confirmed"] in (
        "yes",
        "no",
    ):
        return ChoiceAnswer(flag=values["confirmed"] == "yes", text=values["account"])
    raise ValueError("Choose an assigned Snoop response.")
