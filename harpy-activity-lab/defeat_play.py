"""Activity fields for HarpyEngine's original Defeat decisions."""

from dataclasses import asdict

from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m2_ui import entities, menu, text
from girlframe.discord_adapter.m3_defeat import LABELS
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m3_choices import DEFEAT_HIGH, DEFEAT_LOW, DEFEAT_MID

DEFEAT = "defeat"
DEFEAT_CHOICES = frozenset(
    {
        "defeat_select",
        "defeat_tag_gift",
        "defeat_alternative",
        "defeat_accept_alternative",
    }
)


def defeat_choice(decision):
    kind = decision["kind"]
    detail = decision["defeat"]
    offer = None
    if kind == "defeat_select":
        fields = consequence_fields(decision)
    elif kind == "defeat_tag_gift":
        fields = [
            Field(
                "options",
                "Offer a Tag",
                (("give", "Give a Tag"), ("decline", "Decline to give a Tag")),
            ),
            text("text", "Tag label (only if giving)", False),
        ]
    elif kind == "defeat_alternative":
        fields = [
            text("text", "Describe and justify the alternative"),
            menu("number", "Permissions removed", range(detail["permissions"] + 1)),
            Field("flag", "Confirm your ruling", (("yes", "This is equally ruinous"),)),
            text("fields.tag", "Inflicted Tag (optional)", False),
            Field(
                "fields.frame_context",
                "Context of last Girl Asset loss",
                (
                    ("unspecified", "No last Girl Asset loss"),
                    ("inside", "Inside a Frame"),
                    ("outside", "Outside a Frame"),
                ),
            ),
        ]
        for key in ("assets", "identities"):
            if detail[key]:
                fields.append(
                    entities(
                        "fields." + key,
                        "Remove ordinary " + key,
                        detail[key],
                        0,
                        len(detail[key]),
                        False,
                    )
                )
        if detail["foes"]:
            fields.append(
                Field(
                    "fields.helpless_foe",
                    "Foe for resulting Helplessness",
                    tuple((row["token"], row["label"]) for row in detail["foes"]),
                    0,
                    1,
                    required=False,
                )
            )
    else:
        fields = [
            Field(
                "flag",
                "Respond to this exact offer",
                (("yes", "Accept the offer"), ("no", "Decline and choose again")),
            )
        ]
        current = detail["offer"]
        offer = {
            "account": current["account"],
            "permissions": current["permissions_lost"],
            "assets": current["asset_names"],
            "identities": current["identity_names"],
            "tag": current["tag"],
            "outside_frame": current["outside_frame"],
            "foe": current["foe_label"] if current["helpless_foe"] else None,
        }
    return {"schema": [asdict(field) for field in fields], "offer": offer}


def consequence_fields(decision):
    tier = decision["result"]["tier"]
    own = decision["own"] or {}
    allowed = {"low": DEFEAT_LOW, "mid": DEFEAT_MID, "high": DEFEAT_HIGH}[tier]
    detail = decision["defeat"]
    narrative = detail.get("narrative", False)
    can_confirm = narrative and tier == "low" and detail.get("narrative_death_available", False)
    if narrative and not can_confirm:
        allowed = tuple(key for key in allowed if key != "death")
    fields = [
        Field(
            "options",
            "Choose nonlethal consequences"
            if narrative and not can_confirm
            else "Choose your printed consequences",
            tuple((key, LABELS[key]) for key in allowed),
            2 if tier == "high" else 1,
            1 if tier == "mid" else 2,
        ),
        text("text", "Describe the selected consequences"),
    ]
    if can_confirm:
        fields.append(
            Field(
                "flag",
                "If choosing Death, select Death alone and confirm separately",
                (("yes", "End this character’s life and use the campaign’s one death"),),
                0,
                1,
                required=False,
            )
        )
    others = tuple(
        (str(uid), decision["labels"][str(uid)])
        for uid in decision["pilots"]
        if uid != decision["actor"]
    )
    if tier == "mid":
        for family in ("girl", "frame"):
            fields.extend(
                (
                    text(
                        f"fields.{family}_name",
                        f"{family.title()} Void Asset name (Void option)",
                        False,
                    ),
                    text(
                        f"fields.{family}_description",
                        f"{family.title()} Void alteration (Void option)",
                        False,
                    ),
                )
            )
            assets = [
                row
                for row in own["assets"]
                if row["family"] == family and not row["void"] and row.get("intrinsic") is None
            ]
            if assets:
                fields.append(
                    entities(
                        f"fields.{family}_replace",
                        f"Replace an Asset at the {family.title()} cap",
                        assets,
                        0,
                        1,
                        False,
                    )
                )
        if others:
            fields.append(
                Field(
                    "fields.rescuer",
                    "Rescuer (rescue option)",
                    others,
                    0,
                    1,
                    required=False,
                )
            )
    elif tier == "high" and others:
        fields.append(
            Field(
                "fields.tag_giver",
                "Invite a Tag giver (Tag option)",
                others,
                0,
                1,
                required=False,
            )
        )
    elif tier == "low":
        books = tuple(
            (key, key)
            for key, row in CATALOG.items()
            if row["family"] == "girl" and key != own.get("girl")
        )
        fields.append(
            Field(
                "fields.girl_playbook",
                "New Girl playbook (change option)",
                books,
                0,
                1,
                required=False,
            )
        )
        slots = tuple(
            (str(i), name)
            for i, name in enumerate(CATALOG.get(own.get("girl"), {}).get("identities", ()))
        )
        if slots:
            fields.append(
                Field(
                    "fields.amnesiac_slot",
                    "Starting slot for Amnesiac (amnesia option)",
                    slots,
                    0,
                    1,
                    required=False,
                )
            )
    return fields
