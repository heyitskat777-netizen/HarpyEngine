"""Expose native order authority and explicit NPC cast roles in a scene."""

import json

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_orders import NpcOrderService
from girlframe.services.onboarding import WorkflowError

from play_continuations import field, operation

ORIGINS = {
    "broken": "Broken",
    "npc_flirt": "Unresolved NPC Tag",
    "stim_sex": "Stim-Blissed effect",
    "am_secret": "Scrutinized",
    "secretary": "Secretary appointment",
}
INSTRUCTION = field("instruction", "Direct order") | {"paragraph": True}


class SceneOrders:
    def __init__(self, game, channel):
        self.game = game
        self.channel = channel
        self.actors = ActorService(MissionService(game.store))
        self.cast = CastService(self.actors)
        self.npcs = NpcOrderService(game)
        self.plays = ActorPlayService(game)

    def view(self, viewer, room):
        try:
            with self.game.store.engine.connect() as c:
                self.game.unpaused(c)
                lock = self.game.lock(c, self.channel)
                if lock and lock["state"] != "released":
                    return []
            cast = self.cast.view(viewer, self.channel)
        except (ValueError, WorkflowError):
            return []
        roles = [item for item in cast["roles"] if not item["stale"]]
        forms = []
        try:
            direct = self.game.direct_order_targets(viewer, self.channel)
        except (ValueError, WorkflowError):
            direct = None
            try:
                ranked = self.npcs.ranked_preview(viewer, self.channel)
            except (ValueError, WorkflowError):
                ranked = None
            if (
                ranked
                and ranked["revision"] == cast["game_revision"]
                and ranked["targets"]
            ):
                targets = [
                    (json.dumps({"issuer": ranked["issuer"], "target": uid}), label)
                    for uid, label in ranked["targets"]
                ]
                forms.append(
                    operation(
                        "ranked",
                        "Issue a ranked order as "
                        + (
                            "Handler"
                            if ranked["issuer"]["kind"] == "handler"
                            else "your pilot"
                        ),
                        [field("target", "Original pilot", targets), INSTRUCTION],
                    )
                )
        if direct and direct["revision"] == cast["game_revision"] and direct["targets"]:
            forms.append(
                operation(
                    "direct",
                    "Issue a direct order",
                    [field("target", "Original pilot", direct["targets"]), INSTRUCTION],
                )
            )

        npcs = self.npc_options(viewer, cast["game_revision"], roles)
        if npcs:
            forms.append(
                operation(
                    "npc",
                    "Issue an NPC order",
                    [
                        field("source", "Actual issuer, recipient and source", npcs),
                        INSTRUCTION,
                    ],
                )
            )

        owned = self.actors.choices(viewer)
        if owned["game_revision"] == cast["game_revision"]:
            present = {item["token"] for item in cast["roles"]}
            join = [
                (json.dumps(item["ref"]), item["label"])
                for item in owned["actors"]
                if item["token"] not in present
                and (
                    item["kind"] == "npc"
                    or item["rules"] in ("handler_girl", "clone_am")
                    or item["kind"] == "external_pilot"
                    and item["girl"] == "harpy"
                )
            ]
            leave = [
                (json.dumps(item["ref"]), item["label"])
                for item in cast["roles"]
                if item["own"]
                and item["ref"]["kind"]
                in ("npc", "handler", "clone_am", "external_pilot")
            ]
            for code, label, options in (
                ("join", "Bring a controlled role into the scene", join),
                ("withdraw", "Withdraw a controlled role", leave),
            ):
                if options:
                    forms.append(
                        operation(
                            code,
                            label,
                            [field("actor", "Actual controlled role", options)],
                        )
                    )
            for role in owned["actors"]:
                if role["token"] in present:
                    forms.extend(self.role_forms(viewer, role, cast))
        if not forms:
            return []
        return [
            {
                "id": "orders-and-cast",
                "revision": cast["game_revision"],
                "cast_revision": cast["cast_revision"],
                "action": "scene_orders",
                "instruction": "Orders and scene cast",
                "operations": forms,
                "room": room[0],
                "room_name": room[1],
            }
        ]

    def role_forms(self, viewer, role, cast):
        if not (
            role["rules"] in ("handler_girl", "clone_am")
            or role["kind"] == "external_pilot"
            and role["girl"] == "harpy"
        ):
            return []
        ref = ActorRef.model_validate(role["ref"])
        try:
            preview = self.plays.preview(viewer, self.channel, ref)
        except (WorkflowError, ValueError):
            return []
        if preview["game_revision"] != cast["game_revision"]:
            return []
        token = json.dumps(
            {
                "actor": role["ref"],
                "source": preview["actor"]["source_sha256"],
                "adjudicator": preview["adjudicator"]["ref"],
            }
        )
        forms = []
        if "keep_your_head" not in preview["forbidden_plays"]:
            forms.append(
                operation(
                    "role_keep",
                    "Keep Your Head · " + role["label"],
                    [
                        field("role", "Original role", [(token, role["label"])]),
                        field("context", "Trigger account"),
                        field(
                            "heat",
                            "Heat to spend",
                            [(str(x), str(x)) for x in range((role["heat"] or 0) + 1)],
                        ),
                    ],
                )
            )
        if (
            role["girl"] == "harpy"
            and "check_sensors" not in preview["forbidden_plays"]
        ):
            forms.append(
                operation(
                    "role_sensors",
                    "Check Sensors · " + role["label"],
                    [
                        field("role", "Original role", [(token, role["label"])]),
                        field("context", "Sensor request account"),
                    ],
                )
            )
        return forms

    def npc_options(self, viewer, revision, roles):
        options = []
        if not any(role["ref"]["kind"] == "npc" for role in roles):
            return options
        for role in roles:
            ref = role["ref"]
            if ref["kind"] != "pilot":
                continue
            for origin, label in ORIGINS.items():
                try:
                    data = self.npcs.preview(
                        viewer, self.channel, int(ref["entity"]), origin_kind=origin
                    )
                except (ValueError, WorkflowError):
                    continue
                if data["revision"] != revision:
                    continue
                for issuer in data["issuers"]:
                    token = json.dumps(
                        {
                            "actor": issuer["ref"],
                            "target": ref["entity"],
                            "origin": origin,
                            "condition": issuer["condition"],
                        }
                    )
                    options.append(
                        (token, f"{issuer['label']} → {role['label']} · {label}")
                    )
        return options

    def perform(self, viewer, key, data):
        revision, cast_revision = data["revision"], data["cast_revision"]
        if type(revision) is not int or type(cast_revision) is not int:
            raise ValueError("Reopen the current order and cast form.")
        action, values = (data["answer"][key] for key in ("operation", "values"))
        if action in ("role_keep", "role_sensors"):
            ref = json.loads(values["role"])
            return self.plays.begin(
                viewer,
                key,
                self.channel,
                ActorRef.model_validate(ref["actor"]),
                ref["source"],
                ActorRef.model_validate(ref["adjudicator"])
                if ref["adjudicator"]
                else None,
                cast_revision,
                PlayInput(
                    play="keep_your_head" if action == "role_keep" else "check_sensors",
                    context=values["context"],
                    trigger_confirmed=True,
                    heat=int(values["heat"]) if action == "role_keep" else 0,
                ),
            )
        if action in ("join", "withdraw") and values.keys() == {"actor"}:
            ref = ActorRef.model_validate_json(values["actor"])
            if ref.kind not in ("npc", "handler", "clone_am", "external_pilot"):
                raise WorkflowError("Choose an original controlled role.")
            return self.cast.change(
                viewer, key, self.channel, revision, cast_revision, action, ref
            )
        if action == "direct" and values.keys() == {"target", "instruction"}:
            return self.game.issue_order(
                viewer,
                key,
                self.channel,
                int(values["target"]),
                values["instruction"],
                expected_revision=revision,
            )
        if action == "ranked" and values.keys() == {"target", "instruction"}:
            target = json.loads(values["target"])
            return self.npcs.issue(
                viewer,
                key,
                self.channel,
                ActorRef.model_validate(target["issuer"]),
                int(target["target"]),
                revision,
                values["instruction"],
                origin_kind="ranked",
            )
        if action == "npc" and values.keys() == {"source", "instruction"}:
            source = json.loads(values["source"])
            origin = source["origin"]
            if origin not in ORIGINS:
                raise ValueError("Choose a supported original order source.")
            return self.npcs.issue(
                viewer,
                key,
                self.channel,
                ActorRef.model_validate(source["actor"]),
                int(source["target"]),
                revision,
                values["instruction"],
                origin_kind=origin,
                source_effect=source["condition"] if origin == "stim_sex" else None,
            )
        raise ValueError("Choose the fields for the current scene order.")
