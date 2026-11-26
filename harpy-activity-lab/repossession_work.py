"""Forms for the original captured Harpy and its separately owned decisions."""

from girlframe.engine.creation import AssetChoice
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_conversion import MockingbirdPackage
from girlframe.engine.npc_bonds import NPC_ROLES
from girlframe.services.m3_handler_conversion import HandlerConversionService
from girlframe.services.native_form_fields import Field

ACCOUNT = Field("account", "Describe the actual physical or factual record", paragraph=True)
CONFIRM = (("confirm", "Confirm"),)
REVIEW = (("yes", "Confirm actual result"), ("no", "Reject the proposed result"))


def options(rows):
    return tuple((row["token"], row["label"]) for row in rows)


def pick(values, key):
    return (values.get(key) or (None,))[0]


def form(key, label, *fields):
    return {"id": key, "label": label, "fields": fields}


class RepossessionWork:
    def __init__(self, store):
        self.service = HandlerConversionService(store)

    def detail(self, viewer, identity):
        initial = identity == "captured"
        data = self.service.menu(viewer, None if initial else identity)
        title = "Harpy repossession"
        text = ""
        forms = []
        if initial:
            if data["candidates"]:
                forms = [
                    form(
                        "open",
                        "File captured Harpy",
                        Field("actor", "Current captured Harpy", options(data["candidates"])),
                    )
                ]
            return data, title, text, forms
        phase = data["phase"]
        text = "Filed stage · " + phase.title()
        if data.get("package"):
            package = data["package"]
            text += (
                "\n"
                + package["appearance"]
                + "\n"
                + "\n".join(a["name"] + " · " + a["description"] for a in package["assets"])
            )
        if phase == "complete":
            if data["claimable"]:
                forms = [
                    form("claim", "Claim the completed source", Field("confirm", "Claim", CONFIRM))
                ]
        elif data["pending_physical"] and data["judge"]:
            text += "\n" + data["physicals"][-1]["account"]
            forms = [
                form(
                    "physical_review",
                    "Verify physical outcome",
                    Field("allow", "Factual review", REVIEW),
                    ACCOUNT,
                )
            ]
        elif (
            phase in ("captured", "extracted")
            and data["owns_physical"]
            and not data["pending_physical"]
        ):
            fields = [ACCOUNT]
            if phase == "extracted":
                if not data["bases"]:
                    return data, title, text + "\nAwaiting an eligible Foundation Base.", []
                fields.append(
                    Field(
                        "destination",
                        "Foundation Base",
                        tuple((x["id"], x["label"]) for x in data["bases"]),
                    )
                )
            verb = "extract" if phase == "captured" else "transport"
            forms = [form(verb, "File actual " + verb, *fields)]
        elif phase == "transported" and data["judge"]:
            forms = [
                form(
                    "treat",
                    "Record completed treatment",
                    Field("purge", "Actual poisons purged", paragraph=True),
                    Field("organs", "Actual organ treatment", paragraph=True),
                    Field("conditioning", "Actual reprogramming", paragraph=True),
                    Field(
                        "recovery",
                        "Body condition",
                        (("awake", "Waking confirmed"), ("unchanged", "Condition unchanged")),
                    ),
                )
            ]
        elif phase == "treated" and data["owner"]:
            if not data["girls"] or not data["npcs"]:
                return data, title, text + "\nAwaiting eligible Bond counterparts.", []
            assets = tuple((name, name) for name in CATALOG["MOCKINGBIRD"]["assets"])
            roles = tuple(
                (str(index), label) for index, label in enumerate(NPC_ROLES["MOCKINGBIRD"])
            )
            npcs = options(data["npcs"])
            forms = [
                form(
                    "package",
                    "File Mockingbird package",
                    Field("assets", "Two Girl Assets", assets, 2, 2),
                    Field("description1", "First Asset description", paragraph=True),
                    Field("description2", "Second Asset description", paragraph=True),
                    Field("void", "Selected Asset altered by Void", assets),
                    Field("appearance", "Post-treatment appearance", paragraph=True),
                    Field("girl", "Original personal Bond", options(data["girls"])),
                    Field("role", "NPC Bond role", roles),
                    Field("npc", "NPC Bond counterpart", npcs),
                    Field("role2", "Optional second NPC Bond role", roles, required=False),
                    Field("npc2", "Optional second NPC counterpart", npcs, required=False),
                )
            ]
        elif phase == "package" and data["judge"]:
            positions = tuple(
                (str(index), str(index + 1)) for index in range(len(data["girls"]) + 1)
            )
            forms = [
                form(
                    "review",
                    "Review the conversion package",
                    Field("position", "Status position (first is highest)", positions),
                    ACCOUNT,
                )
            ]
        elif phase == "ready" and data["owner"]:
            text += f"\nStatus position · {data['status_position'] + 1}"
            forms = [
                form(
                    "complete",
                    "Confirm my activation",
                    Field("confirm", "Exact approved package", CONFIRM),
                )
            ]
        return data, title, text, forms

    def write(self, viewer, key, identity, revision, verb, data, values):
        args = viewer, key, identity, revision
        text = values.get("account", "")
        if verb == "open":
            ref = next(
                row["actor"] for row in data["candidates"] if row["token"] == pick(values, "actor")
            )
            return self.service.open(viewer, key, revision, ActorRef.model_validate(ref))
        if verb in ("extract", "transport"):
            destination = next(
                (
                    tuple(row["cell"])
                    for row in data["bases"]
                    if row["id"] == pick(values, "destination")
                ),
                None,
            )
            return self.service.physical(*args, verb, text, destination)
        if verb == "physical_review":
            return self.service.review_physical(*args, pick(values, "allow") == "yes", text)
        if verb == "treat":
            return self.service.treat(
                *args,
                values["purge"],
                values["organs"],
                values["conditioning"],
                pick(values, "recovery") == "awake",
            )
        if verb == "package":
            girls = {row["token"]: ActorRef.model_validate(row["ref"]) for row in data["girls"]}
            npcs = {row["token"]: ActorRef.model_validate(row["ref"]) for row in data["npcs"]}
            if ("role2" in values) != ("npc2" in values):
                raise ValueError("Choose both parts of the second NPC Bond.")
            npc_bonds = [(int(pick(values, "role")), npcs[pick(values, "npc")])]
            if "npc2" in values:
                npc_bonds.append((int(pick(values, "role2")), npcs[pick(values, "npc2")]))
            first, second = values["assets"]
            package = MockingbirdPackage(
                assets=(
                    AssetChoice(name=first, description=values["description1"]),
                    AssetChoice(name=second, description=values["description2"]),
                ),
                void_asset=pick(values, "void"),
                girl_bond=girls[pick(values, "girl")],
                npc_bonds=tuple(npc_bonds),
                appearance=values["appearance"],
            )
            return self.service.package(*args, package)
        if verb == "review":
            return self.service.review(*args, int(pick(values, "position")), text)
        if verb == "complete":
            return self.service.complete(*args)
        if verb == "claim":
            return self.service.claim(*args)
        raise ValueError("Choose the current repossession decision.")
