"""Web fields for source-owned Changeling and Red Queen effects."""

import json

from girlframe.engine import m3_changeling as changeling
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.onboarding import WorkflowError

CHANGELING_CHOICES = {
    "changeling_low_erase": "Blank Slate · Choose the Identity",
    "changeling_recent": "Blank Slate · File the recent memory window",
    "changeling_clay_owner": "Body of Clay · Choose the physical changes",
    "changeling_clay_handler": "Body of Clay · File the assigned changes",
    "changeling_taste": "Body of Clay · Review the changes",
}
MEMORY_CHOICES = {
    "red_queen_memory_category": "Red Queen · Choose what to extract",
    "red_queen_memory_handler": "Red Queen · Choose the additional memory category",
    "red_queen_memory_links": "Red Queen · File the linked memories",
}
COURT_CHOICES = {
    "red_queen_consult": "Consult the Court · Recall and Decree",
    "red_queen_questions": "One-Girl Panopticon · Choose your questions",
    "red_queen_answers": "One-Girl Panopticon · Answer the chosen questions",
    "red_queen_reciprocal": "One-Girl Panopticon · Choose your reciprocal question",
    "red_queen_reciprocal_answer": "One-Girl Panopticon · Your reciprocal answer",
    "red_queen_tag": "One-Girl Panopticon · Record the noticed observer",
}
COURT_SELECTIONS = frozenset({"red_queen_consult", "red_queen_questions", "red_queen_reciprocal"})
CHOICES = CHANGELING_CHOICES | MEMORY_CHOICES | COURT_CHOICES
SOURCE_PLAYS = frozenset(
    {
        "changeling_blank_slate",
        "changeling_body_of_clay",
        "red_queen_memory",
        "red_queen_consult",
        "red_queen_panopticon",
    }
)
SAVED = frozenset({"changeling_copy", "red_queen_restore"})


def choice_fields(kind, data, field, account, yes_no):
    if kind == "red_queen_consult":
        ams = [(row["id"], row["label"]) for row in data["ams"]]
        fields = (
            [
                field(
                    "options",
                    "Court AMs to recall",
                    ams,
                    required=bool(data["minimum"]),
                    multiple=data["maximum"] > 1,
                )
            ]
            if ams and data["maximum"]
            else []
        )
        if data["low"]:
            return fields + [
                field(
                    "queen",
                    "Person who receives the Queen",
                    [(row["id"], row["label"]) for row in data["targets"]],
                ),
            ]
        fields.append(field("text", "Your Decree") | {"paragraph": True})
        if data["high"]:
            fields.append(field("advice", "Self-borne Court AM to ask for advice", ams))
        return fields
    if kind in ("red_queen_questions", "red_queen_reciprocal"):
        fields = [
            field(
                "options",
                "Printed questions",
                data["questions"],
                required=bool(data["minimum"]),
                multiple=data["maximum"] > 1,
            )
        ]
        if kind == "red_queen_questions":
            fields.append(field("tag", "Optional observation Tag", required=False))
        return fields
    if kind in ("red_queen_answers", "red_queen_reciprocal_answer"):
        return [
            field("answer:" + key, text) | {"paragraph": True} for key, text in data["questions"]
        ]
    if kind == "red_queen_tag":
        return [
            field("flag", "Give the observer a Tag?", yes_no),
            field("text", "Your Tag, if giving one", required=False),
        ]
    if kind == "changeling_low_erase":
        return [
            field("identity", "Your Identity to erase", data["identities"]),
            account,
        ]
    if kind == "changeling_recent":
        return [
            field("start_event", "Start of the recent memory window", data.get("anchors")),
            field(
                "earlier_event",
                "Other recorded start event, if applicable",
                required=False,
            ),
            account,
        ]
    if kind == "changeling_taste":
        return [
            field("taste", "Appearance approval", yes_no),
            field("tag", "Your Tag if you answer no", required=False),
            account,
        ]
    if kind.startswith("changeling_clay_"):
        fields = [field(name, label, required=False) for name, label in data["facets"]]
        if data["copies"]:
            fields.append(
                field(
                    "copy",
                    "Or copy a disclosed appearance",
                    [(x["id"], x["label"]) for x in data["copies"]],
                    required=False,
                )
            )
        return [*fields, account]
    if kind != "red_queen_memory_links":
        fields = [
            field("category", "Memory category", data["categories"]),
            field("scope", "Person, place, day, or time range"),
            field(
                "years",
                "Time range is one year or longer, if applicable",
                yes_no,
                required=False,
            ),
        ]
        if kind == "red_queen_memory_category" and data["ams"]:
            fields.append(field("am", "Court AM to install", data["ams"]))
        return fields
    fields = []
    for i, category in enumerate(data["categories"]):
        label = f"{category['kind'].title()} · {category['scope']}"
        fields += [field(f"memories{i}", label + " · Memories, one per line") | {"paragraph": True}]
        if data["identities"]:
            fields.append(
                field(
                    f"identities{i}",
                    "Linked Identities",
                    data["identities"],
                    required=False,
                    multiple=True,
                )
            )
    return fields


def choice_answer(kind, values):
    if kind in COURT_SELECTIONS:
        selected = values.get("options")
        picked = (selected,) if isinstance(selected, str) else tuple(selected or ())
        return ChoiceAnswer(
            options=picked,
            text=values.get("text", ""),
            fields={key: values[key] for key in ("queen", "advice", "tag") if key in values},
        )
    if kind in ("red_queen_answers", "red_queen_reciprocal_answer"):
        return ChoiceAnswer(
            fields={key[7:]: value for key, value in values.items() if key.startswith("answer:")}
        )
    if kind == "red_queen_tag":
        if values.get("flag") not in ("yes", "no"):
            raise WorkflowError("Choose your actual response.")
        return ChoiceAnswer(flag=values["flag"] == "yes", text=values.get("text", ""))
    if kind == "changeling_low_erase":
        return ChoiceAnswer(denied=(values["identity"],), text=values["account"])
    if kind == "changeling_recent":
        return ChoiceAnswer(
            fields={"start_event": values.get("earlier_event") or values["start_event"]},
            text=values["account"],
        )
    if kind == "changeling_taste":
        approve = values["taste"] == "yes"
        return ChoiceAnswer(
            flag=approve, text=values["account"] if approve else values.get("tag", "")
        )
    if kind.startswith("changeling_clay_"):
        facets = {key: values[key] for key in changeling.FACET_LABELS if values.get(key)}
        if copy := values.get("copy"):
            if facets:
                raise WorkflowError(
                    "Choose either a disclosed appearance or changes to individual facets."
                )
            return ChoiceAnswer(fields={"copy": copy}, text=values["account"])
        return ChoiceAnswer(options=tuple(facets), fields=facets, text=values["account"])
    if kind == "red_queen_memory_links":
        return ChoiceAnswer(
            fields={
                key: ",".join(value) if key.startswith("identities") else value
                for key, value in values.items()
                if key in ("memories0", "memories1", "identities0", "identities1")
            }
        )
    fields = {"years": "1+"} if values.get("years") == "yes" else {}
    if kind == "red_queen_memory_category" and values.get("am"):
        fields["am"] = values["am"]
    return ChoiceAnswer(options=(values["category"],), fields=fields, text=values["scope"])


def copy_fields(data, field):
    conversations = data["conversations"]
    actor = data["body"]["actor"]
    outgoing = [(x["id"], x["text"]) for x in conversations if x["actor"] == actor]
    incoming = [(x["id"], x["text"]) for x in conversations if x["addressed"] == actor]
    if not (outgoing and incoming and data["copies"]):
        return []
    return [
        field(
            "copy",
            "Disclosed Identity",
            [(json.dumps(x), x["label"]) for x in data["copies"]],
        ),
        field("first", "Your conversation entry", outgoing),
        field("second", "The other person's entry", incoming),
    ]
