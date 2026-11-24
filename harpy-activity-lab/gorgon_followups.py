"""Activity fields for the exact owned choices returned by native Gorgon Plays."""

import json

from girlframe.services.m3_parasite_infection import LOSSES
from girlframe.services.native_form_fields import Field
from girlframe.services.onboarding import WorkflowError

YES_NO = (("yes", "Confirm"), ("no", "Decline"))
ACCOUNT = Field("text", "Describe what the original actors establish", paragraph=True)
VOID_DESCRIPTION = Field(
    "fields.void_description", "Describe the actual Void change", paragraph=True
)


def _options(values):
    if isinstance(values, dict):
        return tuple(values.items())
    return tuple((value, value.replace("_", " ").title()) for value in values)


def fields_for_gorgon(decision):
    detail = decision["detail"]
    kind = detail["kind"]
    if kind == "collateral":
        cards = [
            Field("options", "Actual environmental effects", _options(detail["options"]), maximum=2)
        ]
        if detail["structures"]:
            cards.append(
                Field(
                    "fields.structure",
                    "Actual structure if selected",
                    tuple((item["id"], item["label"]) for item in detail["structures"]),
                    required=False,
                )
            )
        if detail["civilians"]:
            cards.append(
                Field(
                    "fields.civilians",
                    "Actual civilians if selected",
                    tuple((item["id"], item["label"]) for item in detail["civilians"]),
                    minimum=0,
                    maximum=len(detail["civilians"]),
                    required=False,
                )
            )
        return [*cards, ACCOUNT]
    if kind in ("collateral_reach", "attack_judge", "interrupt", "warp"):
        cards = [Field("options", "Actual source outcome", _options(detail["options"]))]
        if kind == "interrupt" and detail["actors"]:
            cards.append(
                Field(
                    "fields.actor",
                    "Actual actor volunteering to interrupt",
                    tuple((json.dumps(item["ref"]), item["label"]) for item in detail["actors"]),
                    required=False,
                )
            )
        if kind == "warp" and "evolve" in detail["options"]:
            cards += [
                Field("fields.name", "New Asset name if evolving", required=False),
                Field(
                    "fields.description",
                    "New Asset description if evolving",
                    paragraph=True,
                    required=False,
                ),
            ]
        return [*cards, ACCOUNT]
    if kind in (
        "hallucinations_heat",
        "shell_heat",
        "conditioning_heat",
        "unreal_heat",
        "infection_heat",
        "hazard_heat",
    ):
        return [Field("number", f"Heat to spend from your current {detail['heat']}")]
    assets = detail.get("assets", {})
    if kind in ("shell_void", "conditioning_void", "unreal_void", "infection_void", "hazard_void"):
        return (
            [Field("options", "Your actual eligible Asset", _options(assets)), ACCOUNT]
            if assets
            else []
        )
    if kind == "hallucinations_day_gain":
        return (
            [
                Field("fields.asset", "Your actual eligible Asset", _options(assets)),
                VOID_DESCRIPTION,
            ]
            if assets
            else []
        )
    if kind == "hallucinations_day_review":
        return [
            Field("flag", f"Confirm uninterrupted exposure on day {detail['day']}", YES_NO),
            ACCOUNT,
        ]
    if kind == "hallucinations_outcome":
        low = detail["tier"] == "low"
        cards = [Field("text", "Name the resulting Identity" if low else "Name the resulting Tag")]
        if low:
            if len(detail["identities"]) < 3 or not assets:
                return []
            cards.extend(
                (
                    Field(
                        "options",
                        "Three actual Identities to erase",
                        _options(detail["identities"]),
                        3,
                        3,
                    ),
                    Field("fields.asset", "Your actual eligible Asset", _options(assets)),
                    VOID_DESCRIPTION,
                )
            )
        return cards
    if kind == "shell_tie":
        return [Field("flag", "Confirm the closest actual role", YES_NO), ACCOUNT]
    if kind in ("shell_choose", "unreal_grow"):
        count = detail["count"]
        options = _options(detail["options"])
        if count > len(options):
            return []
        cards = [Field("options", "Choose the original effects", options, count, count)]
        if kind == "unreal_grow" and detail.get("guards"):
            cards.append(
                Field(
                    "fields.guard",
                    "Additional Core protector if reinforcing",
                    _options(detail["guards"]),
                    required=False,
                )
            )
        return [*cards, ACCOUNT]
    if kind == "unreal_damage":
        return (
            [
                Field(
                    "options",
                    "Original Growth Asset to damage (optional)",
                    _options(assets),
                    required=False,
                )
            ]
            if assets
            else []
        )
    if kind == "conditioning_review":
        return (
            [
                Field("flag", "Verify the original uninterrupted outcome", (("yes", "Confirm"),)),
                ACCOUNT,
            ]
            if detail.get("can_transform")
            else []
        )
    if kind in ("conditioning_erase", "conditioning_resist"):
        return [Field("flag", "Erase the actual marked Tag?", YES_NO)]
    if kind == "infection_low_review":
        if detail["transfer"]:
            return [
                Field(
                    "options",
                    "Return the choice to its original controller",
                    (("transfer", "Return choice"),),
                )
            ]
        return (
            [Field("options", "Three original sheet parts", _options(detail["parts"]), 3, 3)]
            if len(detail["parts"]) >= 3
            else []
        )
    if kind == "infection_loss":
        return [Field("options", "Original loss", tuple(LOSSES.items())), ACCOUNT]
    if kind == "infection_damage":
        return (
            [Field("options", "Original damaged Asset", _options(assets))]
            if assets
            else [
                Field(
                    "confirm",
                    "Confirm there is no eligible actual Asset",
                    (("confirm", "Confirm"),),
                )
            ]
        )
    if kind == "hazard_eject":
        return [
            Field("options", "Original Pilot's response", _options(("eject", "remain"))),
            ACCOUNT,
        ]
    if kind == "hazard_review":
        return (
            [
                Field("flag", "Verify what happened to the original Pilot", (("yes", "Confirm"),)),
                ACCOUNT,
            ]
            if detail.get("can_review_rebirth")
            else []
        )
    if kind == "hazard_pursue":
        return [ACCOUNT]
    if kind == "hazard_mid":
        return [
            Field(
                "options",
                "Printed consequence",
                (("void", "Gain Void"), ("play", "Mother chooses a Play")),
            )
        ]
    if kind == "hazard_pick_play":
        return [
            Field("options", "Actual approved response", (("keep_your_head", "Keep Your Head"),))
        ]
    if kind in ("contact_consent", "contact_final", "contact_frame_roll"):
        return [Field("flag", "Verify the private original choice", YES_NO)]
    if kind == "contact_review":
        return [Field("flag", "Verify the original situation", YES_NO), ACCOUNT]
    if kind == "contact_conclusion":
        return [
            Field("flag", "Leave an optional Tag?", YES_NO),
            Field("text", "Optional Tag", required=False),
        ]
    if kind == "contact_frame_damage":
        cards = [Field("options", "Original intact Asset to damage", _options(assets))]
        if detail["tier"] == "mid":
            if not detail["void_assets"]:
                return []
            cards += [
                Field(
                    "fields.void_asset", "Actual uncorrupted Asset", _options(detail["void_assets"])
                ),
                VOID_DESCRIPTION,
                Field("flag", "Expose the Core?", YES_NO),
            ]
        return cards
    if kind == "contact_frame_consequence":
        return [
            Field(
                "confirm",
                "Resolve the immediate aftermath",
                (
                    (("yes", "Confirm survivors"), ("intervene", "Offer one combat Play"))
                    if detail["can_intervene"]
                    else (("yes", "Confirm survivors"),)
                ),
            ),
            ACCOUNT,
        ]
    return []


def normalize_choice(kind, answer):
    """Convert a few native form encodings without replacing engine choice checks."""
    value = dict(answer)
    if kind == "battle_counter" and value.get("options") == ["pass"]:
        value["options"] = []
        value["flag"] = False
    if kind == "gorgon_infection_damage" and value.get("confirm") == "confirm":
        value.pop("confirm")
    if kind == "dive_effect" and value.get("confirm") == "directive":
        value.pop("confirm")
    if kind == "gorgon_contact_frame_consequence":
        confirm = value.pop("confirm", None)
        if confirm == "intervene":
            value["options"] = ["intervene"]
        elif confirm == "yes":
            value["flag"] = True
        else:
            raise WorkflowError("Choose the actual private aftermath first.")
    if kind == "harpy_off_duty_hide":
        fields = dict(value.get("fields", {}))
        fields["identities"] = json.dumps(
            [line.strip() for line in fields.get("identities", "").splitlines() if line.strip()]
        )
        value["fields"] = fields
    return value
