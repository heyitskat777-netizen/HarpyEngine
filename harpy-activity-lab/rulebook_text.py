"""Verified presentation text from the supplied book; native IDs remain unchanged."""

import json
from pathlib import Path

from girlframe.engine.bonds import PROMPTS as ENGINE_PROMPTS
from girlframe.engine.creation_details import DESIRES as ENGINE_DESIRES
from girlframe.engine.creation_details import MAXIMS as ENGINE_MAXIMS
from girlframe.engine.creation_details import STANDARDS as ENGINE_STANDARDS
from girlframe.engine.m2 import sensor_question_text as engine_sensor_question_text
from girlframe.engine.npc_bonds import NPC_ROLES as ENGINE_NPC_ROLES

BOOK = json.loads(Path(__file__).with_name("rulebook-text.json").read_text(encoding="utf-8"))
BOND_PROMPTS = {girl: tuple(entry["text"]) for girl, entry in BOOK["bonds"].items()}
assert {girl: len(values) for girl, values in BOND_PROMPTS.items()} == {
    girl: len(values) for girl, values in ENGINE_PROMPTS.items()
}
FLIRT_QUESTION_TEXT = BOOK["questions"]["flirt"]["text"]
FLIRT_QUESTION_TEXT = FLIRT_QUESTION_TEXT | BOOK["questions"]["kicked_puppy"]["text"]
NPC_BOND_ROLES = {girl: tuple(entry["text"]) for girl, entry in BOOK["npc_bonds"].items()}
assert {girl: len(values) for girl, values in NPC_BOND_ROLES.items()} == {
    girl: len(values) for girl, values in ENGINE_NPC_ROLES.items()
}
SNOOP_QUESTION_TEXT = BOOK["questions"]["snoop"]["text"]
DIVE_OPTIONS = BOOK["choices"]["dive"]["text"]
STANDARDS = (*BOOK["choices"]["princess_standards"]["text"], ENGINE_STANDARDS[-1])
MAXIMS = tuple(BOOK["choices"]["oldgen_maxims"]["text"])
DESIRES = tuple(BOOK["choices"]["investor_desires"]["text"])
assert (len(STANDARDS), len(MAXIMS), len(DESIRES)) == (
    len(ENGINE_STANDARDS),
    len(ENGINE_MAXIMS),
    len(ENGINE_DESIRES),
)


def sensor_question_text(question):
    label = engine_sensor_question_text(question)
    return (
        BOOK["questions"]["human_hound"]["text"]["smell"] if label == "What can I smell?" else label
    )


def printed_fields(fields, kind):
    group = "flirt" if "flirt" in kind else "sensors" if "sensors" in kind else None
    if group:
        entry = BOOK["questions"][group]
        for field in fields:
            labels = (
                FLIRT_QUESTION_TEXT
                if group == "flirt"
                else entry["text"]
                | {"consume_smell": BOOK["questions"]["human_hound"]["text"]["smell"]}
            )
            field["options"] = [
                (value, labels.get(value, label)) for value, label in (field.get("options") or ())
            ]
    return fields
