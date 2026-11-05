"""Display actual stored pre-roll modifiers without hiding them in the base value."""

from typing import Any


def expression(receipt: dict[str, Any]) -> str:
    if receipt.get("adjudication") is not None:
        return (
            "MANUAL ADJUDICATION: "
            + str(receipt["pre_total"])
            + " (assigned before Tags; no RNG, dice faces or Heat spent)"
        )
    faces = " + ".join(str(x) for x in receipt["faces"])
    text = faces + " + " + str(receipt.get("base_modifier", receipt["heat"]))
    text += " " + str(receipt.get("modifier_source", "Heat"))
    for modifier in receipt.get("pre_modifiers", []):
        text += " + (" + str(modifier["amount"]) + ") " + str(modifier["source"]).replace("_", " ")
    return text
