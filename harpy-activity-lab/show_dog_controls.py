"""Owned follow-ups to the original Princess Off-Duty appearance."""

from uuid import NAMESPACE_URL, uuid5

from native_scene_forms import form_fields

from girlframe.discord_adapter.m2_forms import Field
from girlframe.engine import m3_show_dog as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_play_support import periods
from girlframe.services.m3_show_dog import ShowDogService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

DESIRES = (
    ("sex", "Wants intimacy with you"),
    ("own", "Wants to own you"),
    ("kill", "Wants to kill you"),
    ("emulate", "Wants to be you"),
)
FIRST_LABELS = {
    "trend": "Start a trend or controversy",
    "public": "Put someone in the public eye",
    "message": "Send an addressed message",
    "quiet": "Smile, obey and take no risks",
}
ACCOUNT = Field("account", "Describe what actually happened", paragraph=True)


def people(data, kind):
    return tuple(
        (ActorRef.model_validate(row["ref"]).model_dump_json(), row["label"]) for row in data[kind]
    )


def operation(key, label, fields):
    return {"id": key, "label": label, "fields": form_fields(fields)}


class ShowDogControls:
    def __init__(self, game):
        self.game = game
        self.periods = periods(game)
        self.service = ShowDogService(game)
        self.world = WorldService(MissionService(game.store))

    def cards(self, viewer, state, period=None):
        for task in self.service.menu(viewer)["tasks"]:
            if not task["pending"]:
                continue
            try:
                data = self.service.menu(viewer, task["id"])
            except (ValueError, WorkflowError):
                continue
            if (
                data["game_revision"] != state.revision
                or data["complete"]
                or (period is not None and data["period"] != period)
            ):
                continue
            operations = self.operations(data)
            if operations:
                yield {
                    "kind": "show_dog",
                    "label": "Show Dog",
                    "id": task["id"],
                    "source_action": data["source_action"],
                    "revision": data["revision"],
                    "operations": operations,
                    "summary": data["account"] if data["can_risk"] else "",
                }

    @staticmethod
    def operations(data):
        result = []
        if data["can_choose"] and data["first"] is None:
            for kind, label in FIRST_LABELS.items():
                targets = people(data, "npcs" if kind == "trend" else "people")
                fields = [ACCOUNT]
                if kind != "quiet":
                    if not targets:
                        continue
                    fields.insert(0, Field("target", "Original subject", targets))
                if kind in ("trend", "public"):
                    fields.append(Field("tag", "Tag to give"))
                elif kind == "message":
                    fields.append(Field("message", "Private addressed message", paragraph=True))
                result.append(operation(kind, label, fields))
        if data["can_choose"] and not data["second"]:
            if data["npcs"]:
                result.append(
                    operation(
                        "second",
                        "File witnessed NPC interest",
                        [
                            Field("npc", "NPC who saw the appearance", people(data, "npcs")),
                            Field("desire", "Printed motivation", DESIRES),
                            ACCOUNT,
                        ],
                    )
                )
            if data["locations"]:
                result.append(
                    operation(
                        "create",
                        "Introduce an NPC at this appearance",
                        [
                            Field("name", "Name"),
                            Field("detail", "Identifying details", paragraph=True),
                            Field(
                                "location",
                                "Current location",
                                tuple((row["id"], row["name"]) for row in data["locations"]),
                            ),
                        ],
                    )
                )
        if data["can_risk"]:
            result.append(
                operation(
                    "risk",
                    "Record the Handler’s ruling",
                    [
                        Field(
                            "punish",
                            "Does the appearance merit a Punishment?",
                            (
                                ("no", "No Punishment"),
                                ("yes", "Assign Punishment"),
                            ),
                        ),
                        ACCOUNT,
                    ],
                )
            )
        return result

    def correspondence(self, viewer):
        with self.game.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            messages = self.service._messages(c, viewer)
            interests = self.service._interests(c, viewer)
        return [
            self.service.view_message(viewer, row["id"]) | {"title": row["label"]}
            for row in messages
        ] + [
            {
                "id": item["id"],
                "title": "Show Dog · Appearance interest",
                "sender": item["princess"],
                "text": item["appearance"],
                "detail": dict(DESIRES)[item["desire"]],
            }
            for row in interests
            for item in (self.service.view_interest(viewer, row["id"]),)
        ]

    def perform(self, viewer, key, period, game_revision, answer):
        if (
            answer.keys() != {"id", "work_revision", "operation", "values"}
            or not isinstance(answer["id"], str)
            or type(answer["work_revision"]) is not int
            or not isinstance(answer["operation"], str)
            or not isinstance(answer["values"], dict)
            or not all(isinstance(item, str) for item in answer["values"].values())
        ):
            raise ValueError("Use the current Show Dog response.")
        identity, kind, values = (answer[name] for name in ("id", "operation", "values"))
        source = self.service.view(viewer, identity)
        if source["period"] != period:
            raise WorkflowError("Reopen the original Off-Duty record.")
        args = (viewer, key, identity, answer["work_revision"], game_revision)
        if kind in rules.FIRST:
            fields = {"account"}
            if kind != "quiet":
                fields.add("target")
            if kind in ("trend", "public"):
                fields.add("tag")
            elif kind == "message":
                fields.add("message")
            if values.keys() != fields:
                raise ValueError("Use the fields for your chosen appearance.")
            return self.service.first(
                *args,
                kind,
                target=ActorRef.model_validate_json(values["target"])
                if "target" in values
                else None,
                tag=values.get("tag", ""),
                message=values.get("message", ""),
                account=values["account"],
            )
        if kind == "second" and values.keys() == {"npc", "desire", "account"}:
            return self.service.second(
                *args,
                ActorRef.model_validate_json(values["npc"]),
                values["desire"],
                values["account"],
            )
        if (
            kind == "risk"
            and values.keys() == {"punish", "account"}
            and values["punish"] in ("yes", "no")
        ):
            return self.service.risk(*args, values["punish"] == "yes", values["account"])
        if kind == "create" and values.keys() == {"location", "name", "detail"}:
            menu = self.service.menu(viewer, identity)
            location = next(
                (row for row in menu["locations"] if row["id"] == values["location"]), None
            )
            if location is None:
                raise WorkflowError("Choose your actual current base or city.")
            identity_key = f"activity-show-dog:{self.game.store.campaign_id}:{viewer.user_id}:{key}"
            npc = Npc(
                id=str(uuid5(NAMESPACE_URL, identity_key)),
                name=values["name"],
                jobs=("civilian",),
                detail=values["detail"],
                controller=viewer.user_id,
                cell=tuple(location["cell"]),
            )
            return self.world.npc(viewer, key, game_revision, npc, show_dog=identity)
        raise ValueError("Use the fields for the original Show Dog response.")
