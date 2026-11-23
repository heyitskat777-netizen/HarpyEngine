"""Activity controls for source-bound Feedback and Void consequences."""

import json
from dataclasses import asdict
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from play_continuations import ACTIONS as CONTINUATION_ACTIONS, PlayContinuations
from girlframe.database import tables
from girlframe.discord_adapter.m2_ui import choice_fields
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_void import FINAL
from girlframe.services import m3_ankou_feedback_sequences as sequence
from girlframe.services.m2_state import load_state
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_play_support import periods
from girlframe.services.m3_prisoner_escape import PrisonerEscapeService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_void import VoidService
from girlframe.services.m3_void_frame_entry import VoidFrameEntryService
from girlframe.services.m3_void_keep import start_view
from girlframe.services.onboarding import WorkflowError


def field(key, label, options=None, *, required=True, multiple=False):
    return {
        "key": key,
        "label": label,
        "options": options,
        "required": required,
        "multiple": multiple,
    }


def options(rows, label="label", key="id"):
    return [(row[key], row[label]) for row in rows]


YES_NO = [("yes", "Yes"), ("no", "No")]
ACCOUNT = field("account", "Your account")
FEEDBACK = [
    ("bond", "Rewrite a Bond"),
    ("purpose", "Ask for purpose"),
    ("tear", "Tear an Asset and retaliate"),
    ("die", "Accept death"),
]
FOLLOWUP_FLAGS = (
    "ankou_feedback",
    "ankou_feedback_child",
    "ankou_effect_child",
    "void_keep",
    "void_frame_entry",
)
GORGON_TYPES = (
    "incubus",
    "doppleganger",
    "jackdaw",
    "mother",
    "sentinel",
    "leviathan",
    "growth",
    "parasite",
)
FRAME_TRANSFORM = ("escape", "overgrown", "abandoned")


def gorgon_fields(data, operation):
    classes = ["aggressive", "dormant", "erratic", "benevolent"]
    if data["gorgon_goals"]:
        classes.append("directed")
    if data["gorgon_leaders"]:
        classes.append("sprite")
    assets = options(data["frame_assets"], "name")
    rows = [
        field("name", "Gorgon name"),
        field("class", "Gorgon Class", [(name, name.title()) for name in classes]),
        field(
            "types",
            "Actual Gorgon Types",
            [(name, name.title()) for name in GORGON_TYPES],
            multiple=True,
        ),
        field("core", "One or two Core-protecting Frame Assets", assets, multiple=True),
        field("weakness", "Core exposure weakness"),
        field(
            "goal",
            "Directed goal",
            options(data["gorgon_goals"], "name"),
            required=False,
        ),
        field("protected_asset", "Directed protective Asset", assets, required=False),
        field(
            "follows",
            "Sprite leader",
            options(data["gorgon_leaders"], "name"),
            required=False,
        ),
        field("sprite_group", "Group of Sprites?", YES_NO, required=False),
    ]
    if operation == "overgrown":
        rows.append(field("alive", "Did the pilot survive?", YES_NO))
    return [*rows, ACCOUNT]


def gorgon_values(data, values, key):
    kind = values["class"]
    extra = {}
    if kind == "directed":
        goal = next(
            (row for row in data["gorgon_goals"] if row["id"] == values.get("goal")),
            None,
        )
        if not goal or not values.get("protected_asset"):
            raise ValueError("Choose the Directed Gorgon’s goal and protective Asset.")
        extra = {
            "goal": {
                k: v for k, v in goal.items() if k in ("kind", "cell", "entity_id")
            },
            "protected_asset": values["protected_asset"],
        }
    elif kind == "sprite":
        extra = {
            "follows": values.get("follows"),
            "sprite_group": values.get("sprite_group") == "yes",
        }
    return {
        "account": values["account"],
        "alive": values.get("alive", "yes") == "yes",
        "gorgon": {
            "id": str(
                uuid5(
                    NAMESPACE_URL, "girlframe:activity:void:" + data["id"] + ":" + key
                )
            ),
            "name": values["name"],
            "cell": data["frame_cell"],
            "gorgon_class": kind,
            "types": values["types"],
            "core_plan": {"assets": values["core"], "weakness": values["weakness"]},
            "assets": [
                {
                    "id": asset["id"],
                    "family": "gorgon",
                    "name": asset["name"],
                    "damaged": asset["damaged"],
                    "void": True,
                    "description": asset["description"] or "Original Frame Asset",
                }
                for asset in data["frame_assets"]
            ],
            **extra,
        },
    }


def feedback_card(data, scenes):
    kind = data["kind"]
    card = {
        "id": data["id"],
        "revision": data["revision"],
        "instruction": "Ankou Feedback",
    }
    if kind == "feedback_sequence":
        if not data["can_activate"]:
            return None
        return card | {
            "action": "feedback_activate",
            "fields": [
                field("channel", "Joined scene", scenes),
                ACCOUNT,
            ],
        }
    if data["can_choose"]:
        if data["pause"]["state"] != "held":
            return card | {
                "action": None,
                "waiting": data["pause"]["state"] == "acquiring",
                "scene": data["pause"]["error"] or "Waiting for the scene to pause.",
            }
        return card | {
            "action": "feedback_choose",
            "fields": [
                field("choice", "Feedback outcome", FEEDBACK),
                field(
                    "target",
                    "Scene participant",
                    options(data["targets"]),
                    required=False,
                ),
                field(
                    "asset", "Asset to tear", options(data["assets"]), required=False
                ),
                field("name", "Name of the rewritten Asset", required=False),
                field(
                    "replace",
                    "Girl Asset to replace at capacity",
                    options(data["assets"]),
                    required=False,
                ),
                field("battle", "Were you in battle?", YES_NO, required=False),
                field(
                    "opponent",
                    "Opponent if losing the last Girl Asset",
                    [("none", "No opponent"), *options(data["targets"])],
                    required=False,
                ),
                ACCOUNT,
            ],
        }
    if data["can_answer"]:
        return card | {
            "action": "feedback_purpose",
            "scene": data["source"].get("account"),
            "fields": [field("given", "Give a purpose?", YES_NO), ACCOUNT],
        }
    if data["can_write"]:
        return card | {
            "action": "feedback_identity",
            "scene": data["source"].get("purpose"),
            "fields": [
                field(
                    "replace",
                    "Identity to replace at capacity",
                    options(data["identities"]),
                    required=False,
                )
            ],
        }
    if data["counter"]:
        return card | {"action": "feedback_reprisal", "fields": [ACCOUNT]}
    return None


def void_operations(data):
    result = []
    stage = data["stage"]
    if stage in FINAL:
        return (
            [("release_protection", [ACCOUNT])]
            if data["guardian_owned"] and data["protection_active"]
            else []
        )
    if data["guardian_owned"] and stage == "allured":
        result.append(("accept_protection", [ACCOUNT]))
    if data["owner"]:
        identities = field(
            "identity",
            "Identity to replace with Free",
            options(data["identities"], "name"),
        )
        if data["question"]:
            result.append(
                (
                    "answer",
                    [
                        field("answer", "Honest answer", YES_NO),
                        field(
                            "honest",
                            "Confirm this answer is honest",
                            [("yes", "I confirm")],
                        ),
                        ACCOUNT,
                    ],
                )
            )
        else:
            if stage == "physical_review":
                result.append(
                    (
                        "propose_occupancy",
                        [
                            field(
                                "mode",
                                "Actual cockpit occupancy",
                                [
                                    ("outside_frame", "Outside my Frame"),
                                    ("inside_frame", "Inside my cockpit"),
                                    ("piloting", "Piloting my Frame"),
                                ],
                            ),
                            ACCOUNT,
                        ],
                    )
                )
            if data["needs_free"]:
                result.append(("begin", [identities, ACCOUNT]))
            if stage == "allured":
                result.append(("propose_approach", [identities, ACCOUNT]))
                if data["guardians"]:
                    result.append(
                        (
                            "protect",
                            [
                                field(
                                    "guardian",
                                    "Present protector",
                                    [
                                        (str(index), row["label"])
                                        for index, row in enumerate(data["guardians"])
                                    ],
                                ),
                                ACCOUNT,
                            ],
                        )
                    )
            if stage == "enclosed" and data["threshold"]["family"] == "frame":
                assets = [
                    (row["id"], row["name"])
                    for row in data["assets"]
                    if row["family"] == "girl" and not row["damaged"]
                ]
                if assets:
                    result.append(
                        (
                            "choose_escape",
                            [field("asset", "Girl Asset to damage", assets), ACCOUNT],
                        )
                    )
            if stage == "rebirth":
                result.extend((("save_rebirth", None), ("rebirth", None)))
            if lessons := data.get("defensive_risk_lessons"):
                result.append(
                    (
                        "use_risk_lesson",
                        [
                            field("lesson", "Unused Risk lesson", options(lessons)),
                            ACCOUNT,
                        ],
                    )
                )
    if data["handler"]:
        if stage == "physical_review" and data["occupancy"]:
            result.append(("confirm_occupancy", [ACCOUNT]))
        if stage == "allured" and data["approach"]:
            result.append(("confirm_approach", [ACCOUNT]))
        if stage in ("abandoned", "overgrown"):
            result.append((stage, gorgon_fields(data, stage)))
        if stage == "enclosed" and data["pending_escape"]:
            result.append(("escape", gorgon_fields(data, "escape")))
    return result


class OwnedFollowups:
    def __init__(self, game, rooms):
        self.game = game
        self.rooms = rooms
        self.ankou = AnkouService(game)
        self.void = VoidService(game.store)
        strain = StrainService(periods(game))
        self.entry = VoidFrameEntryService(strain)
        self.prisoner = PrisonerEscapeService(strain)
        self.movement = MovementService(game)
        self.continuations = PlayContinuations(game)

    def scenes(self, viewer, allowed=None):
        rooms = self.rooms()
        with self.game.store.engine.connect() as c:
            rows = []
            for channel, (_, label) in rooms.items():
                if allowed is not None and channel not in allowed:
                    continue
                try:
                    scene = self.game.scene(c, channel)
                except WorkflowError:
                    continue
                if viewer.user_id in json.loads(scene["participants_json"]):
                    rows.append((str(channel), label))
        return rows

    def view(self, viewer):
        with self.game.store.engine.connect() as c:
            ankou_tasks = [
                row
                for row in self.ankou._tasks(c, viewer)
                if row["pending"]
                and row["label"]
                in ("Ankou — feedback sequence", "Ankou — feedback step")
            ]
        cards = []
        for row in ankou_tasks:
            try:
                data = self.ankou.view(viewer, row["id"])
            except WorkflowError:
                continue
            if card := feedback_card(
                data, self.scenes(viewer) if data["kind"] == "feedback_sequence" else ()
            ):
                cards.append(card)
        for task in self.void.tasks(viewer):
            data = self.void.get(viewer, task["id"])
            operations = void_operations(data)
            if data["owner"] and data["stage"] == "resist_pending":
                resist = start_view(self.game, viewer, data["id"])
                if not resist["child"]:
                    operations.append(
                        (
                            "resist",
                            [
                                field(
                                    "channel",
                                    "Joined scene",
                                    self.scenes(viewer, resist["channels"]),
                                ),
                                field(
                                    "heat",
                                    "Heat",
                                    [
                                        (str(heat), str(heat))
                                        for heat in range(max(0, resist["heat"]) + 1)
                                    ],
                                ),
                                ACCOUNT,
                            ],
                        )
                    )
            if not operations:
                continue
            cards.append(
                {
                    "id": data["id"],
                    "revision": data["game_revision"],
                    "work_revision": data["revision"],
                    "expected": data["expected"],
                    "action": "resolve_void",
                    "instruction": "Void threshold · "
                    + data["stage"].replace("_", " "),
                    "scene": data["question"]
                    or (data["occupancy"] or data["approach"] or {}).get("account"),
                    "operations": [
                        {
                            "id": name,
                            "fields": fields,
                            "initial": {"choice": data["rebirth_choice"], "account": ""}
                            if name in ("save_rebirth", "rebirth")
                            else {"account": "", "alive": True, "gorgon": {}},
                        }
                        for name, fields in operations
                    ],
                }
            )
        cards.extend(self.strain_cards(viewer))
        cards.extend(self.action_cards(viewer))
        cards.extend(self.continuations.view(viewer))
        return cards

    def strain_cards(self, viewer):
        cards = []
        with self.game.store.engine.connect() as c:
            entry_tasks = [
                row for row in self.entry._tasks(c, viewer) if row["pending"]
            ]
            prisoner_tasks = [
                row for row in self.prisoner._tasks(c, viewer) if row["pending"]
            ]
        for task in entry_tasks:
            data = self.entry.view(viewer, task["id"])
            card = {
                "id": data["id"],
                "revision": data["revision"],
                "instruction": "Frame-entry Dive",
            }
            if data.get("can_bind"):
                cards.append(
                    card
                    | {
                        "action": "followup_entry_bind",
                        "fields": [
                            field("channel", "Joined scene", self.scenes(viewer))
                        ],
                    }
                )
            elif data.get("child_descriptor"):
                sheet = self.game.sheet(viewer)
                heat = sheet["heat"]
                cards.append(
                    card
                    | {
                        "action": "followup_entry_dive",
                        "fields": [
                            field(
                                "heat",
                                "Heat to spend",
                                [
                                    (str(value), str(value))
                                    for value in range(max(0, heat) + 1)
                                ],
                            ),
                            ACCOUNT,
                        ],
                    }
                )
            elif not data.get("child"):
                pause = data.get("pause") or {}
                cards.append(
                    card
                    | {
                        "action": None,
                        "waiting": pause.get("state") == "acquiring",
                        "scene": data.get("gap")
                        or pause.get("error")
                        or "Waiting for the scene pause or a prior Void consequence.",
                    }
                )
        for task in prisoner_tasks:
            data = self.prisoner.view(viewer, task["id"])
            card = {
                "id": data["work"],
                "revision": data["revision"],
                "instruction": "Prisoner breakout · " + data["prisoner"],
            }
            if data["can_move"] and data["channel"] in self.rooms():
                try:
                    movement = self.movement.menu(viewer, data["channel"])
                except WorkflowError:
                    movement = None
                if movement and any(
                    row["ref"] == data["actor"] for row in movement["actors"]
                ):
                    cards.append(
                        card
                        | {
                            "id": data["id"],
                            "action": "followup_prisoner_move",
                            "fields": [
                                field(
                                    "x",
                                    "Destination X",
                                    [
                                        (str(x), str(x))
                                        for x in range(
                                            movement["minimum"][0],
                                            movement["maximum"][0] + 1,
                                        )
                                    ],
                                ),
                                field(
                                    "y",
                                    "Destination Y",
                                    [
                                        (str(y), str(y))
                                        for y in range(
                                            movement["minimum"][1],
                                            movement["maximum"][1] + 1,
                                        )
                                    ],
                                ),
                                ACCOUNT,
                            ],
                        }
                    )
            evidence = [("held:" + row["id"], row["label"]) for row in data["grips"]]
            if data["can_fail"]:
                evidence += [
                    ("failed:" + row["id"], row["label"]) for row in data["movements"]
                ]
            if evidence:
                cards.append(
                    card
                    | {
                        "action": "followup_prisoner_outcome",
                        "fields": [
                            field("outcome", "Actual evidence", evidence),
                            ACCOUNT,
                        ],
                    }
                )
        return cards

    def action_cards(self, viewer):
        cards = []
        table = tables.m2["m2_actions"]
        channels = tuple(map(str, self.rooms()))
        with self.game.store.engine.connect() as c:
            active = [
                self.game.action(c, identity)
                for identity in c.scalars(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.channel_id.in_(channels),
                        table.c.state.not_in(("complete", "aborted")),
                    )
                )
            ]
        actions = {row["id"]: row for row in active if self.is_followup(row)}
        for row in actions.values():
            if (
                row["actor_id"] == str(viewer.user_id)
                and row["state"] == "ready_to_roll"
            ):
                cards.append(
                    {
                        "id": row["id"],
                        "revision": row["revision"],
                        "action": "followup_roll",
                        "instruction": "Roll " + row["data"]["play"].replace("_", " "),
                    }
                )
        for row in self.game.choices(viewer):
            if row["action_id"] not in actions:
                continue
            data = self.game.decision(viewer, row["id"])
            card = {
                "id": row["id"],
                "revision": row["revision"],
                "action": "followup_decision",
                "instruction": row["kind"].replace("_", " "),
            }
            if detail := data.get("ankou_feedback"):
                card |= self.action_feedback(row["kind"], detail)
            elif row["kind"] == "tag_window":
                card["fixed_answer"] = {"options": ["pass"]}
            else:
                card["decision_fields"] = [asdict(spec) for spec in choice_fields(data)]
            cards.append(card)
        return cards

    @staticmethod
    def is_followup(row):
        return any(row["data"].get(flag) for flag in FOLLOWUP_FLAGS)

    @staticmethod
    def action_feedback(kind, detail):
        if kind == "ankou_feedback_choice":
            return {
                "fields": [
                    field("choice", "Feedback outcome", FEEDBACK),
                    field(
                        "target",
                        "Actual person",
                        options(detail["people"], key="token"),
                        required=False,
                    ),
                    field(
                        "bond_target",
                        "Eligible Bond",
                        options(
                            [x for x in detail["people"] if x["bond_rewriteable"]],
                            key="token",
                        ),
                        required=False,
                    ),
                    field(
                        "asset",
                        "Accessible Asset",
                        options(
                            [
                                x
                                for x in detail["assets"]
                                if not x["void"]
                                and x["tear_accessible"]
                                and x["tear_supported"]
                            ],
                            "name",
                        ),
                        required=False,
                    ),
                    field("name", "Rewritten Asset name", required=False),
                    field(
                        "replace",
                        "Girl Asset to replace at capacity",
                        options(
                            [x for x in detail["assets"] if x["bond_replaceable"]],
                            "name",
                        ),
                        required=False,
                    ),
                    ACCOUNT,
                ]
            }
        if kind == "ankou_feedback_purpose":
            return {
                "scene": detail.get("request"),
                "fields": [field("given", "Give a purpose?", YES_NO), ACCOUNT],
            }
        if kind == "ankou_feedback_identity":
            return {
                "scene": detail.get("purpose"),
                "fields": [
                    field(
                        "replace",
                        "Identity to replace at capacity",
                        options(
                            [
                                x
                                for x in detail["identities"]
                                if x["purpose_replaceable"]
                            ],
                            "name",
                        ),
                        required=False,
                    )
                ],
            }
        return {"fields": [ACCOUNT]}

    def perform(self, viewer, key, data):
        if not {"id", "revision", "action", "answer"} <= data.keys():
            raise ValueError("Choose the assigned follow-up.")
        identity, revision, action, answer = (
            data[k] for k in ("id", "revision", "action", "answer")
        )
        if (
            not isinstance(identity, str)
            or type(revision) is not int
            or not isinstance(answer, dict)
        ):
            raise ValueError("Choose an assigned follow-up.")
        if action == "resolve_void":
            return self.resolve_void(viewer, key, identity, revision, data, answer)
        if action in CONTINUATION_ACTIONS:
            return self.continuations.perform(viewer, key, data)
        if action == "followup_roll":
            with self.game.store.engine.connect() as c:
                if not self.is_followup(self.game.action(c, identity)):
                    raise WorkflowError("Open the original Play to roll its dice.")
            return self.game.roll(viewer, key, identity)
        if action == "followup_decision":
            return self.action_decision(viewer, key, identity, revision, answer)
        if action == "followup_entry_bind":
            return self.entry.bind_venue(
                viewer, key, identity, revision, int(answer["channel"])
            )
        if action == "followup_entry_dive":
            detail = self.entry.view(viewer, identity)
            descriptor = detail.get("child_descriptor")
            if not descriptor or detail["revision"] != revision:
                raise WorkflowError("Reopen the assigned Frame-entry Dive.")
            sheet = self.game.sheet(viewer)
            return self.begin(
                viewer,
                key,
                descriptor["channel"],
                sheet["revision"],
                "dive_deep",
                identity,
                answer["account"],
                int(answer["heat"]),
                parent=descriptor["parent"],
            )
        if action in ("followup_prisoner_move", "followup_prisoner_outcome"):
            data = self.prisoner.view(viewer, identity)
            if data["revision"] != revision or data["type"] != "attempt":
                raise WorkflowError("Reopen the original breakout attempt.")
            if action == "followup_prisoner_move" and data["can_move"]:
                return self.movement.move(
                    viewer,
                    key,
                    revision,
                    data["channel"],
                    ActorRef.model_validate(data["actor"]),
                    (int(answer["x"]), int(answer["y"])),
                    account=answer["account"],
                )
            if action == "followup_prisoner_outcome":
                from strain_special import prisoner_outcome

                _, submit, _ = prisoner_outcome(self.prisoner, data)
                return submit(
                    viewer,
                    key,
                    {"outcome": (answer["outcome"],), "account": answer["account"]},
                )
            raise WorkflowError(
                "This movement belongs to the actual prisoner’s controller."
            )
        if action == "feedback_activate":
            channel = int(answer["channel"])
            if str(channel) not in dict(self.scenes(viewer)):
                raise WorkflowError(
                    "Join the Activity scene before starting Feedback there."
                )
            return sequence.activate(
                self.game, viewer, key, identity, channel, revision, answer["account"]
            )
        args = (self.game, viewer, key, identity, revision)
        if action == "feedback_purpose":
            if answer.get("given") not in ("yes", "no"):
                raise ValueError("Choose an explicit answer for this purpose request.")
            return sequence.answer_purpose(
                *args, answer["given"] == "yes", answer["account"]
            )
        if action == "feedback_identity":
            return sequence.write_purpose(*args, answer.get("replace"))
        detail = self.ankou.view(viewer, identity)
        if action == "feedback_choose" and detail.get("can_choose"):
            targets = {
                row["id"]: ActorRef.model_validate(row["ref"])
                for row in detail["targets"]
            }
            return sequence.choose(
                *args,
                answer["choice"],
                targets.get(answer.get("target")),
                answer["account"],
                asset=answer.get("asset"),
                replace=answer.get("replace"),
                name=answer.get("name"),
                in_battle=(answer["battle"] == "yes") if answer.get("battle") else None,
                opponent=targets.get(answer.get("opponent")),
                no_opponent=answer.get("opponent") == "none",
            )
        if action == "feedback_reprisal" and (counter := detail.get("counter")):
            target = ActorRef.model_validate(counter["body"]["target"])
            with self.game.store.engine.connect() as c:
                sheet = load_state(c, self.game.store.campaign_id).sheets[
                    str(viewer.user_id)
                ]
            return self.begin(
                viewer,
                key,
                counter["channel"],
                sheet.revision,
                counter["body"]["allowed"][0],
                identity,
                answer["account"],
                sheet.heat,
                target=target,
            )
        raise WorkflowError(
            "This Feedback step belongs to another account or is complete."
        )

    def begin(
        self,
        viewer,
        key,
        channel,
        revision,
        play,
        source,
        account,
        heat,
        *,
        target=None,
        parent=None,
    ):
        return self.game.begin(
            viewer,
            key,
            int(channel),
            revision,
            PlayInput(
                play=play,
                source_work=source,
                context=account,
                heat=heat,
                trigger_confirmed=True,
                parent=parent,
                target=int(target.entity)
                if target and target.kind == "pilot"
                else None,
                target_actor=target
                if target and target.kind in ("npc", "handler")
                else None,
            ),
        )

    def action_decision(self, viewer, key, identity, revision, answer):
        data = self.game.decision(viewer, identity)
        with self.game.store.engine.connect() as c:
            if not self.is_followup(self.game.action(c, data["action_id"])):
                raise WorkflowError("Open the original Play to answer this decision.")
        detail = data.get("ankou_feedback")
        kind = data["kind"]
        if kind == "ankou_feedback_child":
            return self.begin(
                viewer,
                key,
                data["channel"],
                detail["sheet_revision"],
                detail["reprisal_play"],
                detail["id"],
                answer["account"],
                detail["heat"],
                target=ActorRef.model_validate(detail["target"]),
                parent=data["parent"],
            )
        if kind == "ankou_feedback_choice":
            chosen = answer["choice"]
            fields = {}
            if chosen == "bond":
                fields = {"target": answer["bond_target"], "name": answer["name"]}
                if answer.get("replace"):
                    fields["replace"] = answer["replace"]
            elif chosen != "die":
                fields["target"] = answer["target"]
                if chosen == "tear":
                    fields["asset"] = answer["asset"]
            answer = {"options": [chosen], "fields": fields, "text": answer["account"]}
        elif kind == "ankou_feedback_purpose":
            answer = {"flag": answer["given"] == "yes", "text": answer["account"]}
        elif kind == "ankou_feedback_identity":
            answer = {
                "fields": {"replace": answer["replace"]}
                if answer.get("replace")
                else {}
            }
        return self.game.respond(
            viewer,
            key,
            identity,
            revision,
            ChoiceAnswer.model_validate_json(json.dumps(answer)),
        )

    def resolve_void(self, viewer, key, identity, revision, request, answer):
        op, values = answer["operation"], answer["values"]
        detail = self.void.get(viewer, identity)
        if op == "resist":
            resist = start_view(self.game, viewer, identity)
            channel = int(values["channel"])
            if channel not in resist["channels"] or resist["child"]:
                raise WorkflowError(
                    "Resume the original resistance in its actual scene."
                )
            return self.begin(
                viewer,
                key,
                channel,
                resist["sheet_revision"],
                "keep_your_head",
                identity,
                values["account"],
                int(values["heat"]),
                parent=resist["parent"],
            )
        if op == "answer":
            if (
                values.get("answer") not in ("yes", "no")
                or values.get("honest") != "yes"
            ):
                raise ValueError("Choose an explicit answer to this question.")
            values = values | {"answer": values["answer"] == "yes", "honest": True}
        elif op == "protect":
            values = values | {
                "guardian": detail["guardians"][int(values["guardian"])]["ref"]
            }
        elif op in FRAME_TRANSFORM and detail["handler"]:
            values = gorgon_values(detail, values, key)
        return self.void.respond(
            viewer,
            key,
            identity,
            request["work_revision"],
            revision,
            request["expected"],
            op,
            values,
        )
