"""Activity projection of native compulsory Frame replacement work."""

import json

from girlframe.engine.fanbase import DEMOGRAPHICS, QUALITIES
from girlframe.engine.m3_frame_state import Package, Preferences
from girlframe.engine.shared_setup import AM_ROLES
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_replacement import COURT, PACKAGE, ROOTS, ReplacementService
from girlframe.services.onboarding import WorkflowError


def labels(values):
    return [(name, name) for name in values]


def forms(data, field, op, yes_no, registry):
    kind = data["kind"]
    if kind == COURT:
        return [
            op(
                "court",
                "Respond to the Court assignment",
                [field("accepted", "Receive " + data["role"] + "?", yes_no)],
            )
        ]
    if kind == PACKAGE:
        frame = data["preferences"]["frame"]
        fields = [
            field("explanation", "Explain the supplied package"),
        ]
        for index in range(5):
            fields.extend(
                [
                    field(
                        f"name{index}",
                        f"Supplied Asset {index + 1} name (optional)",
                        required=False,
                    ),
                    field(
                        f"description{index}",
                        f"Asset {index + 1} description",
                        required=False,
                    ),
                    field(
                        f"damaged{index}",
                        f"Asset {index + 1} damaged?",
                        yes_no,
                        required=False,
                    ),
                    field(
                        f"void{index}",
                        f"Asset {index + 1} Void-altered?",
                        yes_no,
                        required=False,
                    ),
                ]
            )
        if registry:
            extras = [
                (entry.id, entry.title)
                for entry in registry.entries
                if entry.scope == "frame"
                and entry.kind in ("play", "mechanic")
                and entry.verified
                and entry.module in registry.enabled_modules
            ]
            fields.append(
                field(
                    "rules",
                    "Additional approved abilities",
                    extras,
                    required=False,
                    multiple=True,
                )
            )
        if frame == "CONSUME":
            fields.append(
                field(
                    "consume_hunger",
                    "Starting hunger",
                    labels(("Quiet", "Gnawing", "Ravenous")),
                )
            )
        elif frame == "DOCTORDOCTOR MK. II":
            fields.append(
                field(
                    "obsolescence",
                    "Marked Obsolescence boxes",
                    labels(map(str, range(8))),
                )
            )
        elif frame == "CHANGELING" and data["bond_targets"]:
            fields.append(
                field(
                    "psych_strings",
                    "Starting Psych Strings",
                    [(str(uid), name) for uid, name in data["bond_targets"]],
                    required=False,
                    multiple=True,
                )
            )
        return [op("package", "File free replacement package", fields)]
    if data["ready"]:
        fields = [field("confirm", "Confirm the exact reviewed package", (("yes", "Install"),))]
        if data["firearm"]["needs_replacement"]:
            fields.append(
                field(
                    "firearm_replace",
                    "Replace one of your non-Void Girl Assets",
                    [(item["id"], item["label"]) for item in data["firearm"]["replacements"]],
                )
            )
        return [
            op(
                "apply:" + str(data["package_revision"]),
                "Install reviewed replacement",
                fields,
            )
        ]
    result = []
    for frame, name in data["frames"]:
        fields = [
            field("frame_name", "Frame name", required=False),
            field("frame_appearance", "Frame appearance", required=False),
        ]
        if frame == "THE PRINCE":
            demographics = labels(DEMOGRAPHICS) + [("custom:1", "Custom demographic")]
            qualities = labels(QUALITIES) + [
                ("custom:1", "Custom quality 1"),
                ("custom:2", "Custom quality 2"),
            ]
            fields.extend(
                [
                    field(
                        "demographics",
                        "Choose two fan demographics",
                        demographics,
                        multiple=True,
                    ),
                    field(
                        "demanded",
                        "Choose two demanded qualities",
                        qualities,
                        multiple=True,
                    ),
                    field(
                        "rejected",
                        "Choose two rejected qualities",
                        qualities,
                        multiple=True,
                    ),
                    field("custom_demographic", "Custom demographic", required=False),
                    field("custom_quality_1", "Custom quality 1", required=False),
                    field("custom_quality_2", "Custom quality 2", required=False),
                ]
            )
        elif frame == "THE RED QUEEN":
            fields.extend(
                [
                    field("court_role", "External Court role", labels(AM_ROLES)),
                    field(
                        "court_target",
                        "Proposed Court recipient",
                        [(str(uid), name) for uid, name in data["people"]],
                    ),
                ]
            )
        result.append(op("propose:" + frame, "Propose " + name, fields))
    return result


def package_summary(data, registry):
    package = data.get("package")
    if package is None:
        return None
    preferences = data["preferences"]
    people = {str(uid): name for uid, name in data["people"]}
    rule_titles = {entry.id: entry.title for entry in registry.entries} if registry else {}
    frame = dict(data["frames"]).get(preferences["frame"], preferences["frame"])
    description = [f"Replacement Frame · {frame}"]
    for key, label in (("frame_name", "Name"), ("frame_appearance", "Appearance")):
        if preferences[key]:
            description.append(f"{label} · {preferences[key]}")
    if preferences["court_role"]:
        recipient = people.get(str(preferences["court_target"]), "Original recipient")
        description.append(f"Court assignment · {preferences['court_role']} / {recipient}")
    if fanbase := preferences["fanbase"]:
        for key, label in (
            ("demographics", "Fan demographics"),
            ("demanded", "Demanded qualities"),
            ("rejected", "Rejected qualities"),
        ):
            custom = (
                {"custom:1": fanbase["custom_demographic"]}
                if key == "demographics"
                else {
                    "custom:1": fanbase["custom_quality_1"],
                    "custom:2": fanbase["custom_quality_2"],
                }
            )
            choices = ", ".join(custom.get(value, value) for value in fanbase[key])
            if choices:
                description.append(f"{label} · {choices}")
    if package["psych_strings"]:
        targets = ", ".join(
            people.get(str(uid), "Original Bond holder") for uid in package["psych_strings"]
        )
        description.append(f"Psych Strings · {targets}")
    return "\n".join(
        [
            *description,
            package["explanation"],
            *(
                f"{asset['name']}: {asset['description']}"
                + (" · damaged" if asset["damaged"] else "")
                + (" · Void-altered" if asset["void"] else "")
                for asset in package["assets"]
            ),
            *(rule_titles.get(rule, rule) for rule in package["additional_rules"]),
            *(
                [f"Starting hunger · {package['consume_hunger']}"]
                if package.get("consume_hunger")
                else []
            ),
            *(
                [f"Obsolescence · {package['obsolescence_marked']}"]
                if package.get("obsolescence_marked") is not None
                else []
            ),
        ]
    )


class ReplacementForms:
    def __init__(self, game):
        self.service = ReplacementService(MissionService(game.store))

    def view(self, viewer, field, op, yes_no):
        try:
            rows = self.service.missions.owned_work(viewer)
        except WorkflowError:
            return
        for row in rows:
            if row["kind"] not in (*ROOTS, PACKAGE, COURT) or row["owner_id"] != str(
                viewer.user_id
            ):
                continue
            data = self.service.get(viewer, row["id"])
            if data["state"] != "resolved":
                yield (
                    data,
                    forms(data, field, op, yes_no, self.service.missions.access.registry),
                    package_summary(data, self.service.missions.access.registry),
                )

    def perform(self, viewer, key, identity, revision, game_revision, operation, values):
        args = (viewer, key, identity, revision, game_revision)
        if operation.startswith("propose:"):
            frame = operation.split(":", 1)[1]
            preferences = {
                "frame": frame,
                "frame_name": values.get("frame_name", ""),
                "frame_appearance": values.get("frame_appearance", ""),
            }
            if frame == "THE PRINCE":
                preferences["fanbase"] = {
                    key: values[key]
                    for key in (
                        "demographics",
                        "demanded",
                        "rejected",
                        "custom_demographic",
                        "custom_quality_1",
                        "custom_quality_2",
                    )
                    if key in values
                }
            elif frame == "THE RED QUEEN":
                preferences |= {
                    "court_role": values["court_role"],
                    "court_target": values["court_target"],
                }
            return self.service.propose(
                *args, Preferences.model_validate_json(json.dumps(preferences))
            )
        if operation == "court" and values["accepted"] in ("yes", "no"):
            return self.service.answer_court(*args, values["accepted"] == "yes")
        if operation.startswith("apply:") and values.get("confirm") == "yes":
            return self.service.apply(
                *args,
                int(operation.split(":", 1)[1]),
                firearm_replace=values.get("firearm_replace"),
            )
        if operation == "package":
            package = {
                "assets": [
                    {
                        "name": values[f"name{index}"],
                        "description": values[f"description{index}"],
                        "damaged": values.get(f"damaged{index}") == "yes",
                        "void": values.get(f"void{index}") == "yes",
                    }
                    for index in range(5)
                    if values.get(f"name{index}")
                ],
                "additional_rules": values.get("rules", []),
                "explanation": values["explanation"],
                "consume_hunger": values.get("consume_hunger"),
                "obsolescence_marked": int(values["obsolescence"])
                if "obsolescence" in values
                else None,
                "psych_strings": values.get("psych_strings", []),
            }
            return self.service.quote(*args, Package.model_validate_json(json.dumps(package)))
        raise ValueError("Choose an assigned Frame replacement operation.")
