"""Handler-side Off-Duty review using the native cycle and world services."""

import json

from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_janus_storage import ids as stored_ids
from girlframe.engine.m3_off_duty import HANDLER_SCENES, HandlerContext
from girlframe.engine.m3_scientist_lab import LabAnswer, LabProposal
from girlframe.engine.m3_trainer_phrases import PHRASES
from girlframe.engine.m3_world import ClassChange, Movement
from girlframe.engine.m3_world_state import Goal, Gorgon, Location
from girlframe.services.m2_state import load_state
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

CLASSES = ("dormant", "erratic", "directed", "sprite", "benevolent")


def account_ids(values):
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value.isascii() or not value.isdecimal()
        for value in values
    ):
        raise ValueError("Choose current participants.")
    return tuple(map(int, values))


class OffDutyReview:
    def __init__(self, cycle):
        self.cycle = cycle
        self.world = WorldService(cycle.missions)

    def view(self, viewer, review):
        handler = viewer.user_id == review["handler"]
        scene = review["handler_scene"]
        if not handler and scene is None:
            return None
        card = {
            "handler": handler,
            "phase": review["phase"],
            "attendance": {
                "summary": scene["summary"],
                "confirmed": viewer.user_id in scene["acknowledgements"],
                "remaining": len(
                    set(scene["participants"]) - set(scene["acknowledgements"])
                ),
            }
            if scene is not None
            else None,
        }
        if scene and scene["kind"] == "scientist_lab":
            attendance = card["attendance"]
            attendance["lab"] = scene["lab"]
            if not handler and not attendance["confirmed"]:
                with self.cycle.store.engine.connect() as connection:
                    state = load_state(connection, self.cycle.store.campaign_id)
                    actor = current_ref(state, viewer.user_id)
                    if scene["character_ids"].get(actor.entity) == actor.incarnation:
                        stored = stored_ids(state, actor)
                        assets = [x for x in state.sheets[actor.entity].assets if x.family == "girl"]
                        attendance["lab_assets"] = {
                            "restore": [(x.id, x.name) for x in assets if x.void and x.id not in stored],
                            "replace": [(x.id, x.name) for x in assets],
                        }
        if scene and scene["kind"] == "trainer_conditioning":
            card["attendance"]["phrase"] = dict(PHRASES)[scene["conditioning_phrase"]]
        if not handler or review["phase"] != "active":
            return card
        with self.cycle.store.engine.connect() as connection:
            period = self.cycle.periods._get(connection, review["id"])
            state = load_state(connection, self.cycle.store.campaign_id)
            pending = self.cycle.periods._pending(connection, period.id)
            if (state.revision, period.revision) != (
                review["game_revision"],
                review["revision"],
            ):
                return card
            recovered = all(
                str(uid) in period.ended_characters
                or (progress := period.progress.get(str(uid))) is not None
                and progress.recovered
                for uid in period.pilots
            )
            card["recovery_pending"] = not recovered
            card["pending_count"] = review["pending_count"]
            card["pending_kinds"] = sorted({row["kind"] for row in review["work"]})
            card["handler_id"] = str(review["handler"])
            card["participants"] = review["participants"]
            card["status_ready"] = recovered and all(
                row["kind"] == "off_duty_status_review" for row in pending
            )
        if scene is None:
            world = self.world.get(viewer, private=True)["world"]
            card["scene_kinds"] = [
                kind
                for kind in HANDLER_SCENES
                if world or kind not in ("prisoner", "npc_employment")
            ]
            if review["scientist_lab_available"]:
                card["scene_kinds"].append("scientist_lab")
            if review["trainer_can_install_speak"]:
                card["scene_kinds"].append("trainer_conditioning")
                card["conditioning_phrases"] = [
                    (key, label) for key, label in PHRASES
                ]
            card["npcs"] = [
                {
                    "id": "npc:" + row["id"],
                    "label": row["name"],
                    "prisoner": "prisoner" in row["jobs"],
                    "employment": row["employment"],
                    "tags": [(tag["id"], tag["label"]) for tag in row["tags"]],
                }
                for row in (world or {}).get("npcs", ())
                if row["alive"] and row["captive_of"] is None
            ]
            card["prisoners"] = [
                {
                    "id": "pilot:" + row["id"],
                    "label": row["name"],
                    "custodian": str(row["custodian"]),
                }
                for row in (world or {}).get("pilots", ())
                if row["alive"] and row["custody"] in ("captured", "transported")
            ]
        if card["status_ready"] and review["status_reviewed"]:
            card["finish"] = self.advancement(
                viewer, review["id"], review["game_revision"]
            )
        return card

    def advancement(self, viewer, period, revision):
        source = self.world.advancement(viewer)
        world = source["world"]
        if not world or source["game_revision"] != revision:
            return None
        if period in world.get("completed_off_duty", ()):
            return {"moves": [], "changes": [], "goals": [], "classes": []}
        gorgons = [
            row
            for row in world["gorgons"]
            if row["alive"] and row["id"] in source["advancing_gorgons"]
        ]
        locations = [
            Location.model_validate_json(
                json.dumps(
                    {k: v for k, v in row.items() if k != "official_allegations"}
                )
            )
            for row in world["locations"]
        ]
        return {
            "moves": [
                {
                    "id": row["id"],
                    "label": row["name"],
                    "cells": source["directed_steps"][row["id"]],
                }
                for row in gorgons
                if row["gorgon_class"] == "directed"
            ],
            "changes": [
                {
                    "id": row["id"],
                    "label": row["name"],
                    "assets": [(asset["id"], asset["name"]) for asset in row["assets"]],
                    "leaders": [
                        (other["id"], other["name"])
                        for other in gorgons
                        if other["id"] != row["id"]
                        and other["gorgon_class"] != "sprite"
                        and other["types"] == row["types"]
                    ],
                }
                for row in gorgons
                if row["gorgon_class"] == "aggressive"
                and not any(
                    location.cell == tuple(row["cell"] or ()) and location.operational
                    for location in locations
                )
            ],
            "classes": CLASSES,
            "goals": [
                ("location:" + location.id, location.name)
                for location in locations
                if location.condition != "destroyed"
            ]
            + [
                ("npc:" + row["id"], row["name"])
                for row in world["npcs"]
                if row["alive"] and row["cell"] is not None
            ]
            + [("cell", "Map square")],
        }

    def perform(self, args, action, answer):
        viewer = args[0]
        if action == "activate_period" and not answer:
            return self.cycle.activate(*args)
        if action == "acknowledge_handler_scene":
            if not answer:
                return self.cycle.acknowledge(*args, None)
            if answer.keys() == {"lab"}:
                return self.cycle.acknowledge(*args, None, LabAnswer.model_validate(answer["lab"]))
        if action == "review_status" and answer.keys() == {"order", "account"}:
            return self.cycle.review_status(
                *args, account_ids(answer["order"]), answer["account"]
            )
        if action == "set_handler_scene":
            fields = {
                "scientist_lab": {"lab"},
                "trainer_conditioning": {"conditioning_phrase"},
            }.get(answer.get("kind"), set())
            if answer.keys() != fields | {
                "kind", "participants", "summary", "recipient", "context",
            }:
                raise ValueError("Complete the selected Handler scene's fields.")
            phrase = answer.get("conditioning_phrase")
            if "conditioning_phrase" in fields and phrase not in dict(PHRASES):
                raise ValueError("Choose a printed Conditioning Phrase.")
            recipient = answer["recipient"]
            return self.cycle.handler_scene(
                *args,
                answer["kind"],
                (viewer.user_id, *account_ids(answer["participants"])),
                answer["summary"],
                account_ids([recipient])[0] if recipient else None,
                HandlerContext.model_validate_json(json.dumps(answer["context"]))
                if answer["context"] is not None
                else None,
                conditioning_phrase=phrase,
                lab=LabProposal.model_validate(answer["lab"]) if "lab" in fields else None,
            )
        if action == "finish_period" and answer.keys() == {"moves", "changes"}:
            if not isinstance(answer["moves"], list) or not isinstance(
                answer["changes"], list
            ):
                raise ValueError("Review each required world effect.")
            moves = tuple(
                Movement.model_validate_json(json.dumps(row)) for row in answer["moves"]
            )
            changes = ()
            if answer["changes"]:
                source = self.world.advancement(viewer)
                if not source["world"]:
                    raise WorkflowError(
                        "Refresh the actual world before filing this review."
                    )
                gorgons = {
                    row["id"]: row
                    for row in source["world"]["gorgons"]
                    if row["id"] in source["advancing_gorgons"]
                }
                changes = tuple(class_change(row, gorgons) for row in answer["changes"])
            return self.cycle.finish(*args, moves, changes)
        raise ValueError("Choose a current Off-Duty review action.")


def class_change(change, gorgons):
    if (
        not isinstance(change, dict)
        or change.keys()
        != {"id", "class", "goal", "protect", "leader", "group", "account"}
        or not isinstance(change["id"], str)
        or change["id"] not in gorgons
        or change["class"] not in CLASSES
    ):
        raise ValueError("Review the actual Gorgon and its Class change.")
    original = Gorgon.model_validate_json(json.dumps(gorgons[change["id"]]))
    goal = (
        Goal.model_validate_json(json.dumps(change["goal"])) if change["goal"] else None
    )
    replacement = Gorgon.model_validate_json(
        original.model_copy(
            update={
                "gorgon_class": change["class"],
                "goal": goal,
                "protected_asset": change["protect"],
                "follows": change["leader"],
                "sprite_group": change["group"],
            }
        ).model_dump_json()
    )
    return ClassChange(
        gorgon=original.id, replacement=replacement, account=change["account"]
    )
