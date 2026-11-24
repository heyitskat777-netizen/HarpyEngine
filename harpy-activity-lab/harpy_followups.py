"""Native Dive choices and original table text for alternate Harpy Plays."""

from girlframe.discord_adapter.m3_dive import LABELS, MANIFESTATIONS
from girlframe.services.native_form_fields import Field

AGREE = (("yes", "Confirm"), ("no", "Decline"))


def labeled(rows, key="id"):
    return tuple((item[key], item["label"]) for item in rows)


def dive_form(decision):
    kind = decision["kind"]
    detail = decision["dive"]
    if kind == "dive_select":
        choices = tuple((key, LABELS[key]) for key in detail["options"])
        return [
            Field("options", "Original Dive effect", choices),
            Field("text", "Describe the connection", paragraph=True),
        ] if choices else [], ""
    if kind == "dive_table_answer":
        return [Field("text", "Your own answer", paragraph=True)], detail["question"]
    if kind == "dive_table_agreement":
        proposal = detail["proposal"]
        return [
            Field("flag", "Accept this exact Identity proposal?", AGREE),
            Field("text", "Your comments", paragraph=True, required=False),
        ], f"{detail['identity_label']} → {proposal['replacement']}\n{proposal['account']}"
    if kind != "dive_effect":
        return [], ""
    effect = detail["option"]
    if effect in ("call_cockpit_guest", "call_gorgon_relay") and detail["targets"]:
        return [
            Field("fields.target", "Original contact", labeled(detail["targets"], "token")),
            Field("text", "Your invitation or communion", paragraph=True),
        ], ""
    if effect == "call_reclassify_assets":
        assets = detail["assets"]
        return [
            Field(
                "options",
                "Actual Assets moving families",
                labeled(assets),
                minimum=0,
                maximum=max(1, len(assets)),
                required=False,
            ),
            Field(
                "denied",
                "Excess non-Void Assets to replace",
                labeled([x for x in assets if not x["void"]]),
                minimum=0,
                maximum=max(1, len(assets)),
                required=False,
            ),
        ], ""
    if effect == "void_and_unmark_all" and detail["assets"]:
        fields = [
            Field("fields.asset", "Actual uncorrupted Asset", labeled(detail["assets"])),
            Field("text", "Describe the Void alteration", paragraph=True),
        ]
        if detail["storage_available"]:
            fields.append(
                Field(
                    "fields.storage",
                    "Store Void in the linked Harpy",
                    (("yes", "Use the actual linked Harpy"),),
                    required=False,
                )
            )
        return fields, ""
    if effect in ("erase_identity_and_table_question", "table_replaces_identity"):
        return [
            Field("fields.identity", "Original Identity", labeled(detail["identities"])),
            Field("text", "Question or proposed Identity", paragraph=True),
        ], ""
    if effect == "nearby_npcs_gain_void":
        fields = [
            Field("fields." + item["id"], item["label"], MANIFESTATIONS) for item in detail["npcs"]
        ]
        if not fields and detail["has_targets"]:
            fields.append(
                Field(
                    "confirm",
                    "Open the Director's own response",
                    (("directive", "Confirm the nearby effect"),),
                )
            )
        return fields, "The Director keeps its own response." if detail["has_targets"] else ""
    if effect == "locked_cockpit_extraction_requires_frame_consent":
        return [Field("flag", "Confirm the actual cockpit subsumption", (AGREE[0],))], ""
    return [], ""
