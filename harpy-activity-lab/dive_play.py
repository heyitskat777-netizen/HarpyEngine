"""Project HarpyEngine's owned Dive Deep decisions for the Activity."""

from dataclasses import asdict

from girlframe.discord_adapter.m2_ui import entities, menu, text
from girlframe.discord_adapter.m3_dive import LABELS, MANIFESTATIONS
from rulebook_text import DIVE_OPTIONS
from girlframe.discord_adapter.m2_forms import Field

DIVE = "dive_deep"
DIVE_CHOICES = (
    "dive_select",
    "dive_effect",
    "dive_table_answer",
    "dive_table_agreement",
)


def dive_choice(decision):
    detail = decision["dive"]
    kind = decision["kind"]
    prompt = None
    if kind == "dive_select":
        fields = [
            Field(
                "options",
                "Choose one available effect",
                tuple((x, DIVE_OPTIONS.get(x,LABELS[x])) for x in detail["options"]),
            ),
            text("text", "Describe the actual connection"),
        ]
    elif kind == "dive_table_answer":
        prompt = detail["question"]
        fields = [text("text", "Your own answer to the table question")]
    elif kind == "dive_table_agreement":
        proposal = detail["proposal"]
        prompt = (
            f"Replace {detail['identity_label']} with “{proposal['replacement']}”. "
            f"Connection: {proposal['account']}"
        )
        fields = [
            menu("flag", "Accept this exact proposal?", ("yes", "no")),
            text("text", "Comments or proposed revision", False),
        ]
    else:
        option = detail["option"]
        if option in ("erase_identity_and_table_question", "table_replaces_identity"):
            fields = [
                entities(
                    "fields.identity",
                    "Choose the ordinary unprotected Identity",
                    detail["identities"],
                    1,
                    1,
                ),
                text(
                    "text",
                    "Ask the table your question"
                    if option == "erase_identity_and_table_question"
                    else "Propose the new Identity",
                ),
            ]
        elif option == "call_reclassify_assets":
            assets = detail["assets"]
            fields = [
                entities(
                    "options",
                    "Move Assets to their other family",
                    assets,
                    0,
                    max(1, len(assets)),
                    required=False,
                ),
                entities(
                    "denied",
                    "Only if above a cap: replace excess non-Void Assets",
                    [x for x in assets if not x["void"]],
                    0,
                    max(1, len(assets)),
                    required=False,
                ),
            ]
        elif option in ("call_cockpit_guest", "call_gorgon_relay"):
            fields = [
                Field(
                    "fields.target",
                    "Actual cockpit guest or nearby Gorgon",
                    tuple((x["token"], x["label"]) for x in detail["targets"]),
                ),
                text("text", "Describe actual contact"),
            ]
        elif option == "void_and_unmark_all":
            fields = [
                entities(
                    "fields.asset",
                    "Choose your uncorrupted Asset",
                    detail["assets"],
                    1,
                    1,
                ),
                text("text", "Describe the Void alteration"),
            ]
            if detail.get("storage_available"):
                fields.append(
                    menu(
                        "fields.storage",
                        "Store the newly gained Void?",
                        ("yes",),
                        required=False,
                    )
                )
            if detail.get("casualty_parts"):
                fields.extend(
                    [
                        Field(
                            "fields.casualty_part",
                            "Wounded God: infected part to break",
                            tuple(
                                (x["id"].removeprefix("part:"), x["name"])
                                for x in detail["casualty_parts"]
                            ),
                            minimum=0,
                            required=False,
                        ),
                        text(
                            "fields.casualty_site_account",
                            "Actual infected anatomical site if resisting",
                            False,
                        ),
                    ]
                )
        elif option == "nearby_npcs_gain_void":
            fields = [
                Field("fields." + x["id"], "Void: " + x["label"], MANIFESTATIONS)
                for x in detail["npcs"]
            ]
            if not fields and detail["has_targets"]:
                return {
                    "fields": [],
                    "fixed_answer": {},
                    "prompt": "Confirm the nearby effect.",
                }
        else:
            fields = [menu("flag", "Confirm cockpit subsumption", ("yes",))]
    if not fields or any(
        field.required and not field.paragraph and not field.options for field in fields
    ):
        return {
            "fields": [],
            "unavailable": "HarpyEngine has no eligible option for this effect.",
        }
    return {"fields": [asdict(field) for field in fields], "prompt": prompt}
