"""Physical recovery and Cadre invasion controls for the original Harpy source."""

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_physical import HarpyPhysicalService
from girlframe.services.m3_voidspace_invasion import InvasionService
from girlframe.services.native_form_fields import Field
from girlframe.services.onboarding import WorkflowError

KINDS = frozenset({"harpy_physical", "harpy_help", "harpy_invasion"})
ACCOUNT = Field("account", "Describe the actual outcome", paragraph=True)


def operation(verb, label, *fields):
    return {"id": verb, "label": label, "fields": fields}


class HarpyRecovery:
    def __init__(self, game, defeat):
        self.store, self.defeat = game.store, defeat
        self.physical = HarpyPhysicalService(self.store)
        self.invasion = InvasionService(game)

    def tasks(self, connection, state, viewer):
        for task in self.physical._tasks(connection, viewer):
            if task["actionable"]:
                yield (
                    "harpy_help" if task["review"] else "harpy_physical",
                    task["id"],
                    "Review Harpy assistance" if task["review"] else "Harpy Frame and body",
                )
        for identity, _ in self.invasion.tasks(connection, state, viewer):
            yield "harpy_invasion", identity, "Voidspace Invasion"

    def detail(self, viewer, kind, identity):
        if kind == "harpy_invasion":
            data = self.invasion.get(viewer, identity)
            title, text, operations = self.invasion_fields(data)
            return data, title, text, operations
        if kind == "harpy_help":
            data = self.physical.review(viewer, identity)
            return (
                data,
                "Harpy assistance",
                data["body"]["account"],
                [
                    operation(
                        "review",
                        "File physical review",
                        Field(
                            "choice",
                            "Has this help occurred?",
                            (("yes", "Confirm actual help"), ("no", "Decline proposal")),
                        ),
                        ACCOUNT,
                    )
                ]
                if data["state"] != "resolved" and data["can_review"]
                else [],
            )
        actor = ActorRef(kind="external_pilot", entity=identity)
        with self.store.engine.connect() as connection:
            if not any(
                row["id"] == identity and row["actionable"] and not row["review"]
                for row in self.physical._tasks(connection, viewer)
            ):
                raise WorkflowError("Open the original Frame or assistance assigned to you.")
        data = self.physical.get(viewer, actor)
        forms = []
        if data["owner"] and data["locked"]:
            forms.extend(
                operation(verb, label, ACCOUNT)
                for verb, label in (
                    ("allow", "Allow extraction as the Frame"),
                    ("refuse", "Refuse or revoke extraction"),
                    ("open", "Open this cockpit"),
                )
            )
        if data["linked"] and data["extractors"]:
            options = tuple((x["token"], x["label"]) for x in data["extractors"])
            forms.append(
                operation(
                    "extract",
                    "Propose extraction",
                    Field("extractor", "Your source-scene role", options),
                    ACCOUNT,
                )
            )
        if data["owner"] and not data["linked"] and (not data["vitals"] or data["incapacitated"]):
            forms.append(operation("recover", "Request medical help", ACCOUNT))
        return data | {"revision": data["game_revision"]}, "Harpy Frame and body", "", forms

    @staticmethod
    def invasion_fields(data):
        step = data["step"]
        text = data.get("encounter") or ""
        fields = []
        if step == "roll" and data["aces"]:
            fields = [Field("ace", "Original Ace", tuple(data["aces"].items())), ACCOUNT]
        elif step == "review" and data["tier"] in ("mid", "high"):
            text = f"Original dice {data['faces']} · Void modifier {data['modifier']}"
            fields = [Field("account", "Describe the route found", paragraph=True)]
        elif step == "route":
            text = data["route"] + ("\n" + text if text else "")
            fields = (
                [Field("account", "Describe your onward journey", paragraph=True)]
                if data["traveler"]
                else []
            )
        elif step == "encounter" and data["encounters"]:
            fields = [
                Field("target", "Actual encounter", tuple(data["encounters"].items())),
                ACCOUNT,
            ]
        elif step == "gain" and data["assets"]:
            fields = [
                Field("asset", "Eligible Asset", tuple(data["assets"].items())),
                Field("account", "Describe the Void alteration", paragraph=True),
            ]
        return (
            "Voidspace Invasion",
            text,
            [operation(step, "File record", *fields)] if fields else [],
        )

    def write(self, viewer, key, kind, identity, verb, data, values):
        args = viewer, key, identity, data["revision"]
        account = values["account"]
        if kind == "harpy_help":
            return self.physical.confirm(
                *args, accepted=values["choice"] == ("yes",), evidence=account
            )
        if kind == "harpy_physical":
            actor = ActorRef.model_validate(data["actor"])
            physical = viewer, key, actor, data["expected"], verb, account
            if verb in ("allow", "refuse", "open"):
                return self.physical.voice(*physical)
            extract = values.get("extractor", (None,))[0]
            selected = next((x["ref"] for x in data["extractors"] if x["token"] == extract), None)
            return self.physical.propose(
                *physical, extractor=ActorRef.model_validate(selected) if selected else None
            )
        if verb == "roll":
            return self.invasion.start(*args, values["ace"][0], account)
        if verb == "review":
            return self.invasion.route(*args, account)
        if verb == "encounter":
            return self.invasion.encounter(*args, values["target"][0], account)
        if verb == "gain":
            return self.invasion.gain(*args, values["asset"][0], account)
        return self.defeat.propose_route(
            viewer,
            key,
            data["revision"],
            ActorRef.model_validate(data["traveler"]),
            discovery=data["discovery"],
            account=account,
            navigation="",
        )
