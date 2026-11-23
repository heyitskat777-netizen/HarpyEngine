"""Project and file Handler Plays through HarpyEngine's owned-grant service."""

import json

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_dogrunner_dress import DELEGATE_OPTIONS
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_play_state import (
    DRESS_CONTACTS,
    DRESS_ENDINGS,
    DRESS_STEPS,
    EXTRA,
    Effect,
)
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_dogrunner_dress import DressPerformanceService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_successor import SuccessorService, owned as owned_successor
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError

HANDLER_PLAY_STEPS = (
    "handler-play-start",
    "handler-play-submit",
    "handler-play-withdraw",
    "handler-play-warp",
    "handler-play-prepare-off-duty",
    "handler-play-successor",
)
FORMS = frozenset(
    {
        "brief",
        "escalate",
        "expectation",
        "punish",
        "support",
        "mess",
        "off_duty",
        "tracker_intercept",
        "tracker_voyeur",
        "contaminant_warp",
        "dress_them_down",
        "successor_advice",
    }
)
SUPPORT_JOBS = {
    "base_personnel": "Base logistics",
    "mechanic": "Engineering and repair",
    "intelligence_agent": "Intelligence",
    "public_relations": "Public relations",
    "guard": "Security",
    "scientist": "Science",
    "doctor": "Medical",
}
SCENE_EFFECTS = {
    "dress_them_down": "dress_scene",
    "successor_advice": "advice_scene",
}
RULES = {
    "brief": "play.handler.brief",
    "punish": "handler.handler.punish-them",
    "escalate": "handler.handler.escalate-the-situation",
    "support": "handler.handler.introduce-the-support",
    "mess": "handler.handler.mess-with-their-status-tags-or-assets",
    "expectation": "handler.handler.place-an-expectation-on-them",
    "off_duty": "handler.handler.handler-off-duty",
}


class HandlerPlaybook:
    def __init__(self, store, registry, periods):
        self.service = HandlerPlayService(store)
        self.dress = DressPerformanceService(self.service.game)
        self.successor = SuccessorService(store)
        self.periods = periods
        self.pages = {entry.id: entry.source.printed_page for entry in registry.entries}

    @staticmethod
    def available(detail):
        reasons = {
            "punish": "No authorized target and separate executor are on file."
            if not detail["targets"] or not detail["executors"]
            else None,
            "support": "File a campaign map in Battlefield to set up canonical locations."
            if not detail["locations"]
            else None,
            "mess": "No original affected target is on file."
            if not detail["targets"]
            else None,
            "off_duty": "An actual Off-Duty period must be prepared first."
            if not detail["off_duty"]
            else None,
        }
        return [
            {"id": identity, "label": label, "reason": reasons.get(identity)}
            for identity, label in detail["plays"]
            if identity in FORMS
        ]

    def view(self, viewer):
        data = self.service.options(viewer)
        period = self.periods.current(viewer)
        tasks = []
        for task in data["tasks"]:
            detail = self.service.get(viewer, task["id"])
            tasks.append(
                {
                    "id": task["id"],
                    "revision": detail["game_revision"],
                    "state": detail["grant"]["state"],
                    "stale": detail["stale"],
                    "ordinary": detail["grant"]["source"] == "ordinary",
                    "targets": [
                        {key: target[key] for key in ("token", "label", "assets")}
                        for target in detail["targets"]
                    ],
                    "plays": self.available(detail),
                    "executors": [
                        (actor["token"], actor["label"])
                        for actor in detail["executors"]
                    ],
                    "locations": detail["locations"],
                    "observed_moment": detail["observed_moment"],
                }
            )
        return {
            "revision": data["game_revision"],
            "plays": [
                {
                    "id": identity,
                    "label": label,
                    "page": self.pages.get(RULES.get(identity)),
                    "playable": identity in FORMS,
                }
                for identity, label in (*data["plays"], *EXTRA)
            ],
            "targets": data["targets"],
            "support_jobs": list(SUPPORT_JOBS.items()),
            "off_duty_phase": period["phase"] if period else None,
            "warp_zones": data["warp_zones"],
            "scene_effects": {
                "dress_them_down": data["dress_them_down"],
                "successor_advice": data["successor"],
            },
            "dress_steps": DRESS_STEPS,
            "dress_contacts": DRESS_CONTACTS,
            "successor": self.successor_work(viewer) if data["successor"] else None,
            "tasks": tasks,
        }

    def notices(self, viewer):
        with self.service.store.engine.connect() as connection:
            notices = self.service._notices(connection, viewer)
        return [self.service.notice(viewer, item["id"]) for item in notices]

    def successor_work(self, viewer):
        with self.service.store.engine.connect() as connection:
            state = load_state(connection, self.service.store.campaign_id)
            acquisition = owned_successor(self.service.game, connection, state, active_handler(state))
        if acquisition is None:
            return None
        return self.successor.menu(viewer, acquisition.id)

    def dress_work(self, viewer):
        with self.service.store.engine.connect() as connection:
            state = load_state(connection, self.service.store.campaign_id)
            identities = self.dress.tasks(connection, viewer, state)
        cards = []
        for identity in identities:
            try:
                source = self.dress.get(viewer, identity)
            except WorkflowError:
                continue
            phase = source["phase"]
            options = (
                DELEGATE_OPTIONS
                if phase == "delegate"
                else (("performed", "Confirm the recorded contact"),)
                if phase == "contact"
                else ()
            )
            cards.append(
                {
                    "id": identity,
                    "revision": source["revision"],
                    "action": "dress_performance",
                    "instruction": "Dress Them Down · " + source["target"],
                    "dress": {
                        "phase": phase,
                        "contacts": [
                            dict(DRESS_CONTACTS)[key] for key in source["contacts"]
                        ],
                        "options": [*options, ("decline", "Decline the performance")]
                        if options
                        else [],
                    },
                }
            )
        return cards

    def perform_dress(self, viewer, key, data):
        if data.keys() != {"id", "revision", "action", "answer"} or (
            not isinstance(data["id"], str) or type(data["revision"]) is not int
        ):
            raise ValueError("Use your current performance record.")
        answer = data["answer"]
        if (
            not isinstance(answer, dict)
            or answer.keys() != {"step", "account"}
            or not all(isinstance(answer[field], str) for field in ("step", "account"))
        ):
            raise ValueError("Supply the owned performance choice.")
        args = (viewer, key, data["id"], data["revision"])
        if answer["step"] == "finish" and not answer["account"]:
            return self.dress.finish(*args)
        return self.dress.respond(*args, answer["step"], answer["account"])

    def perform(self, viewer, key, step, data, *, scene_channel=None):
        revision = data.get("revision")
        if type(revision) is not int:
            raise ValueError("Use the current Handler Play revision.")
        if step == "handler-play-successor":
            action = data.get("operation")
            fields = {"award": {"account", "advice", "lesson"}, "remove": {"star"}}
            expected = {"id", "revision", "operation"}
            if (
                not isinstance(action, str)
                or action not in fields
                or data.keys() != expected | fields[action]
                or any(not isinstance(value, str) for name, value in data.items() if name != "revision")
            ):
                raise ValueError("Choose the saved advice, later lesson, or actual Star.")
            args = (viewer, key, data["id"], revision)
            if action == "award":
                return self.successor.judge(*args, data["advice"], data["lesson"], data["account"])
            return self.successor.remove(*args, data["star"])
        if step == "handler-play-prepare-off-duty" and data.keys() == {"revision"}:
            return self.periods.begin(viewer, key)
        if (
            step == "handler-play-warp"
            and data.keys() == {"revision", "zone"}
            and isinstance(data["zone"], str)
        ):
            return self.service.start_warp(viewer, key, revision, data["zone"])
        if step == "handler-play-start":
            if not isinstance(data.get("targets"), list):
                raise ValueError("Select the affected pilots.")
            scope = {}
            if data.keys() == {"revision", "targets", "room", "play"}:
                source = (
                    SCENE_EFFECTS.get(data["play"], "ordinary_scene" if data["play"] in RULES else None)
                    if isinstance(data["play"], str)
                    else None
                )
                if source is None or scene_channel is None:
                    raise ValueError("Use the original scene for this Handler Play.")
                scope[source] = scene_channel
            elif data.keys() != {"revision", "targets"}:
                raise ValueError("Select the affected pilots.")
            targets = tuple(
                ActorRef.model_validate_json(json.dumps(ref)) for ref in data["targets"]
            )
            if not targets or any(ref.kind != "pilot" for ref in targets):
                raise ValueError("Select the affected pilots.")
            return self.service.start(viewer, key, revision, targets, **scope)
        identity = data.get("id")
        if not isinstance(identity, str):
            raise TypeError("Choose a saved Handler Play.")
        if step == "handler-play-withdraw" and data.keys() == {"id", "revision"}:
            return self.service.withdraw(viewer, key, identity, revision)
        required = {
            "id",
            "revision",
            "play",
            "account",
            "detail",
            "stakes",
        }
        if step != "handler-play-submit" or data.keys() - {"fields"} != required:
            raise ValueError("Choose the Handler Play and its fields.")
        play = data["play"]
        if not isinstance(play, str) or play not in FORMS:
            raise WorkflowError("This Handler Play has no effect form in the Activity.")
        effect = self.effect(viewer, identity, play, data)
        if effect.dress_needs_performance:
            return self.dress.propose(viewer, key, identity, revision, effect)
        return self.service.submit(viewer, key, identity, revision, play, effect)

    def effect(self, viewer, identity, play, data):
        fields = data.get("fields", {})
        if not isinstance(fields, dict):
            raise TypeError("Use the fields for the selected Play.")
        account = data["account"]
        if play in ("brief", "escalate", "expectation", "successor_advice"):
            if fields:
                raise ValueError("Use the fields for the selected Play.")
            return Effect(
                kind=play, account=account, detail=data["detail"], stakes=data["stakes"]
            )
        detail = self.service.get(viewer, identity)
        if play == "dress_them_down":
            required = {"target", "dress_steps"}
            extras = {"dress_contact", "dress_delegate", "dress_dismissal", "tag"}
            steps = fields.get("dress_steps")
            if not (
                required <= fields.keys() <= required | extras
                and isinstance(steps, list)
                and all(isinstance(step, str) for step in steps)
            ):
                raise ValueError("Choose the original Girl and her printed steps.")
            return Effect(
                kind=play,
                account=account,
                detail=data["detail"],
                target=actor_ref(detail["targets"], fields["target"]),
                dress_steps=tuple(step for step in steps if step not in DRESS_ENDINGS)
                + tuple(step for step in steps if step in DRESS_ENDINGS),
                dress_contact=fields.get("dress_contact") or None,
                dress_delegate=actor_ref(detail["executors"], fields["dress_delegate"])
                if fields.get("dress_delegate")
                else None,
                dress_dismissal=fields.get("dress_dismissal", ""),
                tag=fields.get("tag", ""),
            )
        if play == "support" and fields.keys() == {
            "name",
            "department",
            "location",
            "description",
        }:
            location = next(
                (
                    row
                    for row in detail["location_records"]
                    if row["id"] == fields["location"]
                ),
                None,
            )
            if location is None or fields["department"] not in SUPPORT_JOBS:
                raise ValueError("Choose a campaign location and a support department.")
            employee = Npc(
                id="support-" + identity,
                name=fields["name"],
                jobs=(fields["department"],),
                detail=fields["description"],
                controller=viewer.user_id,
                cell=tuple(location["cell"]),
                revealed=True,
                employment="foundation",
            )
            return Effect(kind="support", account=account, npc=employee)
        if play == "punish" and fields.keys() == {"target", "executor"}:
            return Effect(
                kind="punish",
                account=account,
                target=actor_ref(detail["targets"], fields["target"]),
                executor=actor_ref(detail["executors"], fields["executor"]),
            )
        if play == "off_duty" and not fields and detail["off_duty"]:
            return Effect(kind="off_duty", account=account, off_duty=detail["off_duty"])
        if play in ("tracker_intercept", "tracker_voyeur") and fields.keys() == {
            "target"
        }:
            return Effect(
                kind=play,
                account=account,
                target=actor_ref(detail["targets"], fields["target"]),
                detail=(detail["observed_moment"] or "")
                if play == "tracker_voyeur"
                else "",
            )
        if (
            play == "contaminant_warp"
            and detail["zone"]
            and fields.keys() == {"cell", "feature", "description"}
        ):
            if not isinstance(fields["cell"], str):
                raise TypeError("Enter the actual zone coordinates.")
            x, y = fields["cell"].split(",")
            return Effect(
                kind="contaminant_warp",
                account=account,
                zone=detail["zone"],
                cell=(int(x), int(y)),
                source_label=fields["feature"],
                detail=fields["description"],
            )
        if play == "mess":
            kind = fields.get("kind")
            keys = {"status": "status", "tag": "tag", "damage": "asset"}
            if (
                not isinstance(kind, str)
                or kind not in keys
                or fields.keys() != {"kind", "target", keys[kind]}
            ):
                raise ValueError("Choose a Status, Tag, or Asset effect.")
            value = fields[keys[kind]]
            target = actor_ref(detail["targets"], fields["target"])
            return Effect(
                kind=kind, account=account, target=target, **{keys[kind]: value}
            )
        raise ValueError("Use the fields and prerequisites for the selected Play.")


def actor_ref(actors, token):
    actor = next((actor for actor in actors if actor["token"] == token), None)
    if actor is None:
        raise ValueError("Choose an actor from this Handler Play's saved source.")
    return ActorRef.model_validate(actor["ref"])
