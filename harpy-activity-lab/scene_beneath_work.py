"""Assigned discipline and locked Tags from a saved Put Someone Beneath You."""

import json
from dataclasses import asdict

import sqlalchemy as sa
from alpha_controls import BRUTALIZE
from alpha_controls import COUNTER as ALPHA_COUNTER
from easy_target_controls import CHILD_ACTION as EASY_CHILD_ACTION
from easy_target_controls import EASY
from easy_target_controls import SOURCE_KIND as EASY_CHILD
from handler_punishments import (
    ACTIVITY_ROLE_CASES,
    FOLLOWUPS,
    HandlerPunishments,
    discipline_details,
    instruction_forms,
)
from mockingbird_play import PERSON, complete_conversation, conversation_work
from native_scene_forms import (
    CONSUME_CHILDREN,
    ENFORCEMENT,
    NATIVE_TITLES,
    PANDORA,
    PANDORA_CHILD,
    RISK_CHOICE,
    TAG_DECISIONS,
    is_native_child_choice,
    mounted_roll,
)
from native_scene_forms import choice_supported as native_choice_supported
from play_continuations import ACTIONS as CONTINUATION_ACTIONS
from play_continuations import BODY_CONSEQUENCES, choice_review_source
from specialist_effects import CHOICES as SPECIALIST_CHOICES
from specialist_effects import SOURCE_PLAYS
from wyvern_controls import ESCAPE as WYVERN_ESCAPE
from wyvern_controls import ESCAPE_ACTION as WYVERN_ESCAPE_ACTION

from girlframe.database import tables
from girlframe.discord_adapter.m2_ui import choice_fields
from girlframe.engine import m3_ankou
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_lobotomy_state import OPTIONS
from girlframe.engine.m3_punishments import KINDS
from girlframe.services.m2_state import load_state
from girlframe.services.m3_beneath import (
    discipline_finished,
    discipline_ready,
    work_root,
)
from girlframe.services.m3_lobotomy import LobotomyService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_role_punishments import _latest_work
from girlframe.services.m3_tag_permissions import PermissionService
from girlframe.services.onboarding import WorkflowError

BENEATH = "put_someone_beneath_you"
DISCIPLINE_STEPS = (
    "punishment_helpless",
    "punishment_frame_loss",
    "punishment_paired_identity_heat",
)
ROLE_CASE_STEPS = frozenset({"instruct", "approve", "scene", "attest", "execute"})


class SceneBeneathWork:
    def __init__(self, game, rooms, followups=None):
        self.game = game
        self.rooms = rooms
        self.discipline = PunishmentService(game.store)
        self.permissions = PermissionService(game.store)
        self.surgeries = LobotomyService(game.store)
        self.controls = HandlerPunishments(game)
        self.followups = followups

    def source(self, c, root):
        action = self.game.action(c, root)
        room = self.rooms().get(int(action["channel_id"]))
        if action["data"]["play"] != BENEATH or room is None:
            raise WorkflowError("Open the original confrontation in an Activity scene.")
        return action, room

    def popup_source(self, c, identity):
        action = self.game.action(c, identity)
        while action["parent_id"]:
            action = self.game.action(c, action["parent_id"])
        room = self.rooms().get(int(action["channel_id"]))
        return (action, room) if room else (None, None)

    def role_case_source(self, c, state, identity):
        case = next(
            (
                item
                for item in state.role_punishments
                if item.id == identity
                and item.action
                and item.source_kind in ACTIVITY_ROLE_CASES
                and item.source_kind != "handler_play"
            ),
            None,
        )
        if case:
            action, room = self.popup_source(c, case.action)
            if room:
                return action, room
        return None, None

    def discipline_source(self, c, row):
        original = work_root(self.game, c, row)
        if original is None:
            raise WorkflowError("Open the original discipline workflow.")
        identity = json.loads(original["body_json"])["source_action"]
        action, room = self.source(c, identity)
        if original["scene_id"] != action["scene_id"]:
            raise WorkflowError("The discipline work no longer matches its original scene.")
        return identity, room

    @staticmethod
    def scoped(card, root, room):
        return card | {"root": root, "room": room[0], "room_name": room[1]}

    def legacy_origin(self, c, action, work):
        saved = action["data"].get("beneath_work")
        if action["state"] != "awaiting_choices" or not saved:
            return None
        root = work.get(saved["id"])
        if root is None or root["state"] != "resolved":
            return None
        if not any(
            row["kind"] == "beneath_punishment" for row in self.game.pending(c, action["id"])
        ):
            return None
        return root if discipline_ready(self.game, c, root, work) else None

    def followup_source(self, c, identity, action, state, work):
        if action == "native_scene_roll":
            original = self.game.action(c, identity)
            saved, room = self.popup_source(c, identity)
            return (saved["id"], room) if saved and mounted_roll(self.game, c, original) else None
        if action in (
            "snoop_decision",
            "consume_partake",
            "specialist_choice",
            "native_scene_choice",
            "native_body_consequence",
            "consume_child_play",
            "pandora_child",
            "alpha_counter",
            EASY_CHILD_ACTION,
            WYVERN_ESCAPE_ACTION,
            "native_choice_review",
        ):
            choices = tables.m2["m2_choices"]
            original = c.execute(
                sa.select(choices.c.action_id, choices.c.kind).where(
                    choices.c.campaign_id == self.game.store.campaign_id,
                    choices.c.id == identity,
                )
            ).first()
            if original:
                saved, room = self.popup_source(c, original.action_id)
                native = self.game.action(c, original.action_id)
                if saved and (
                    action == "consume_partake"
                    and original.kind == "consume_partake"
                    or action == "snoop_decision"
                    and saved["data"]["play"] == "snoop"
                    or action == "native_scene_choice"
                    and (
                        native_choice_supported(native["data"]["play"], original.kind)
                        or is_native_child_choice(self.game, c, native, original.kind)
                    )
                    or action == "consume_child_play"
                    and original.kind in CONSUME_CHILDREN
                    or action == "pandora_child"
                    and original.kind == PANDORA_CHILD
                    and native["data"]["play"] == PANDORA
                    or action == "alpha_counter"
                    and original.kind == ALPHA_COUNTER
                    and native["data"]["play"] == BRUTALIZE
                    or action == EASY_CHILD_ACTION
                    and original.kind.partition(":")[0] == EASY_CHILD
                    and native["data"]["play"] == EASY
                    or action == WYVERN_ESCAPE_ACTION
                    and original.kind == WYVERN_ESCAPE
                    and native["data"]["play"] == "wyvern_explore"
                    or action == "native_choice_review"
                    and choice_review_source(native["data"]["play"], original.kind)
                    or action == "native_body_consequence"
                    and saved["data"]["play"] == ENFORCEMENT
                    and original.kind in BODY_CONSEQUENCES
                    or action == "specialist_choice"
                    and (
                        original.kind in SPECIALIST_CHOICES
                        or original.kind in TAG_DECISIONS
                        and native["data"]["play"] in SOURCE_PLAYS
                        or original.kind == RISK_CHOICE
                        and (
                            native["data"]["play"] in NATIVE_TITLES.keys() | SOURCE_PLAYS
                            or is_native_child_choice(self.game, c, native, original.kind)
                        )
                    )
                ):
                    return saved["id"], room
            return None
        if action in CONTINUATION_ACTIONS:
            if not self.followups:
                return None
            original = self.followups.continuations.origin(identity, action, state, work)
            if original:
                saved, room = self.popup_source(c, original)
                if saved:
                    return saved["id"], room
            return None
        if action in ("followup_roll", "followup_decision"):
            if action == "followup_decision":
                choices = tables.m2["m2_choices"]
                identity = c.scalar(
                    sa.select(choices.c.action_id).where(
                        choices.c.campaign_id == self.game.store.campaign_id,
                        choices.c.id == identity,
                    )
                )
                if identity is None:
                    return None
            saved = self.game.action(c, identity)["data"]
            if feedback := saved.get("ankou_effect_child"):
                identity = feedback["id"]
            elif saved.get("void_keep"):
                identity = saved["prepared"]["source_work"]
            else:
                return None
        elif action and action != "resolve_void" and not action.startswith("feedback_"):
            return None
        row = work.get(identity)
        if row is None:
            step = next(
                (x for x in m3_ankou.records(state, m3_ankou.FeedbackStep) if x.id == identity),
                None,
            )
            row = work.get(step.sequence) if step else None
        if row is None or row["kind"] not in (
            "ankou_feedback_sequence",
            "void_threshold",
        ):
            return None
        body = json.loads(row["body_json"])
        if (
            row["kind"] == "void_threshold"
            and body.get("reason") in ("dive_deep", "defeat", "item_transfer")
            and (original := body.get("source_action"))
        ):
            original_action, room = self.popup_source(c, original)
            if original_action and original_action["data"]["play"] in (
                BENEATH,
                "dive_deep",
                "defeat",
                ENFORCEMENT,
            ):
                return original_action["id"], room
        try:
            return self.discipline_source(c, row)
        except WorkflowError:
            return None

    def view(self, viewer, followup_cards=(), role_cards=()):
        uid = str(viewer.user_id)
        cards = []
        with self.game.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.game.store.campaign_id)
            items = _latest_work(c, self.game)
            for card in role_cards:
                if card.get("role_case"):
                    action, room = self.role_case_source(c, state, card["id"])
                    if action:
                        cards.append(
                            self.scoped(card, action["id"], room)
                            | {"specialty": True, "play": action["data"]["play"]}
                        )
            for card in followup_cards:
                if source := self.followup_source(c, card["id"], card["action"], state, items):
                    action, _ = self.popup_source(c, source[0])
                    if card["action"] and self.legacy_origin(c, action, items):
                        card = {
                            "id": card["id"],
                            "revision": card["revision"],
                            "instruction": card["instruction"],
                            "action": "recover_scene_followup",
                            "resume_action": card["action"],
                        }
                    cards.append(
                        self.scoped(card, *source)
                        | {"specialty": True, "play": action["data"]["play"]}
                    )
            for conversation in state.mockingbird.conversations:
                if conversation.ended_event or (
                    str(viewer.user_id) != conversation.actor.entity
                    and not any(
                        party.controller == viewer.user_id for party in conversation.counterparts
                    )
                ):
                    continue
                action, room = self.popup_source(c, conversation.action)
                if action and action["data"]["play"] == PERSON:
                    cards.extend(
                        self.scoped(card, action["id"], room) | {"play": PERSON}
                        for card in conversation_work(self.game, viewer, state, conversation)
                    )
            for row in items.values():
                if row["state"] == "resolved" or row["owner_id"] != uid:
                    continue
                kind = row["kind"]
                if kind not in ("punishment", "punishment_consult", *DISCIPLINE_STEPS):
                    continue
                if kind == "punishment" and json.loads(row["body_json"]).get("lobotomy_id"):
                    continue
                try:
                    root, room = self.discipline_source(c, row)
                except WorkflowError:
                    continue
                card = self.discipline_card(viewer, row, state)
                cards.append(self.scoped(card, root, room))
            surgery_scope = {value.id: value.work_ids for value in state.lobotomies}
            for task in self.surgeries._tasks(c, viewer) if surgery_scope else ():
                for identity in surgery_scope[task["id"]]:
                    try:
                        root, room = self.discipline_source(c, items[identity])
                    except (KeyError, WorkflowError):
                        continue
                    data = self.surgeries.get(viewer, task["id"])
                    cards.append(
                        self.scoped(
                            {
                                "id": task["id"],
                                "revision": data["game_revision"],
                                "action": "surgery_" + data["phase"],
                                "instruction": "Experimental surgery · " + data["patient"],
                                "surgery": data | {"options": OPTIONS},
                            },
                            root,
                            room,
                        )
                    )
                    break
            own_resolutions = [
                row
                for row in self.game.pending_choices(c, viewer)
                if row["kind"] == "tag_resolution"
            ]
            for gate in state.obligations:
                if gate.kind != "tag_rejection_permission" or viewer.user_id not in (
                    gate.owner,
                    gate.target,
                ):
                    continue
                try:
                    _, room = self.source(c, gate.action)
                    data = self.permissions._get(c, viewer, gate.id)
                except WorkflowError:
                    continue
                if not data["active"] and not data["allowed"]:
                    continue
                cards.append(
                    self.scoped(
                        {
                            "id": gate.id,
                            "action": "allow_locked_tag" if data["can_consent"] else None,
                            "revision": state.revision,
                            "expected": data["source_sha256"],
                            "instruction": "Locked Tag · " + data["label"],
                            "read_only": not data["can_consent"],
                            "scene": (
                                "Consent recorded. The Tag bearer still chooses how to respond."
                                if data["allowed"]
                                else "Consent belongs to " + data["locker_label"] + "."
                            ),
                        },
                        gate.action,
                        room,
                    )
                )
                if viewer.user_id == gate.target:
                    for row in own_resolutions:
                        if json.loads(row["body_json"]).get("tag") != gate.details["tag"]:
                            continue
                        decision = self.game.decision(viewer, row["id"])
                        cards.append(
                            self.scoped(
                                {
                                    "id": row["id"],
                                    "action": "resolve_locked_tag",
                                    "revision": row["revision"],
                                    "permission": gate.id,
                                    "instruction": "Resolve locked Tag · " + data["label"],
                                    "decision_fields": [
                                        asdict(spec) for spec in choice_fields(decision)
                                    ],
                                },
                                gate.action,
                                room,
                            )
                        )
        return cards

    def discipline_card(self, viewer, row, state):
        identity = row["id"]
        base = {
            "id": identity,
            "work_revision": row["revision"],
            "revision": state.revision,
        }
        if row["kind"] in DISCIPLINE_STEPS:
            return base | {"action": row["kind"], "instruction": FOLLOWUPS[row["kind"]]}
        data = self.discipline.get(viewer, identity)
        if row["kind"] == "punishment_consult":
            return base | {
                "action": "answer_punishment_consult",
                "instruction": "Review Moderate Punishment",
                "instruction_details": data["summary"],
                "consult_stale": data["stale"],
            }
        base["instruction"] = "Assigned Punishment · " + data["callsign"]
        if consult := data["consultation"]:
            review = self.discipline.get(viewer, consult["id"])
            if consult["state"] != "resolved":
                return base | {
                    "action": None,
                    "scene": "Waiting for the Handler's consultation.",
                }
            if consult["approved"] and not review["stale"]:
                return base | {
                    "action": "apply_approved_punishment",
                    "instruction_details": review["summary"],
                }
        if not (choices := data.get("choices")):
            return base | {"action": None}
        is_handler = viewer.user_id == choices["handler"]
        choices["pilots"] = [
            (uid, label) for uid, label in choices["pilots"] if uid != row["owner_id"]
        ]
        kinds = [
            kind
            for kind, (_, severity) in KINDS.items()
            if (is_handler or severity != "severe")
            and data["required_severity"] in (None, severity)
        ]
        return base | {
            "action": "apply_scene_punishment",
            "forms": instruction_forms(kinds, choices, ()),
            "consult_moderate": not is_handler,
        }

    def perform(self, viewer, key, data):
        identity, step, answer, root = (data.get(k) for k in ("id", "action", "answer", "root"))
        if (
            not all(isinstance(value, str) for value in (identity, step, root))
            or type(data.get("revision")) is not int
        ):
            raise ValueError("Choose an assigned decision in its original scene.")
        if step == "recover_scene_followup":
            return self.recover_followup(viewer, key, identity, root, data["revision"], answer)
        if step in ROLE_CASE_STEPS:
            with self.game.store.engine.connect() as c:
                self.game.authorize(c, viewer, game=False)
                state = load_state(c, self.game.store.campaign_id)
                action, _ = self.role_case_source(c, state, identity)
                if action is None or action["id"] != root:
                    raise WorkflowError("Open the original scene for this Punishment.")
            return self.controls.perform(
                viewer, key, {k: v for k, v in data.items() if k != "root"}
            )
        if step in ("mockingbird_release", "mockingbird_end"):
            with self.game.store.engine.connect() as c:
                self.game.authorize(c, viewer, game=False)
                action, _ = self.popup_source(c, root)
                if action is None or action["id"] != root or action["data"]["play"] != PERSON:
                    raise WorkflowError("Open the original conversation in an Activity scene.")
                state = load_state(c, self.game.store.campaign_id)
            return complete_conversation(
                self.game, viewer, key, root, state, identity, step, answer
            )
        specialty = (
            step in CONTINUATION_ACTIONS
            or step == "resolve_void"
            or step.startswith(("feedback_", "followup_"))
        )
        with self.game.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            if not specialty:
                self.source(c, root)
            if specialty:
                source = self.followup_source(
                    c,
                    identity,
                    step,
                    load_state(c, self.game.store.campaign_id),
                    _latest_work(c, self.game),
                )
                if not self.followups or source is None or source[0] != root:
                    raise WorkflowError("Open this follow-up in its original scene popup.")
            elif step in ("allow_locked_tag", "resolve_locked_tag"):
                permission = identity if step == "allow_locked_tag" else data.get("permission")
                _, gate = self.permissions._gate(c, viewer, permission)
                if gate.action != root:
                    raise WorkflowError("Open the original Tag restriction.")
                if step == "resolve_locked_tag":
                    choice = tables.m2["m2_choices"]
                    row = c.execute(
                        sa.select(choice.c.kind, choice.c.actor_id, choice.c.body_json).where(
                            choice.c.campaign_id == self.game.store.campaign_id,
                            choice.c.id == identity,
                        )
                    ).first()
                    if (
                        row is None
                        or row.kind != "tag_resolution"
                        or row.actor_id != str(viewer.user_id)
                        or json.loads(row.body_json).get("tag") != gate.details["tag"]
                    ):
                        raise WorkflowError(
                            "Only the actual Tag bearer can answer their original Tag decision."
                        )
            elif step in ("surgery_plan", "surgery_responses", "surgery_ready"):
                _, surgery = self.surgeries._get(c, viewer, identity)
                if not any(
                    self.discipline_source(c, self.discipline._row(c, work))[0] == root
                    for work in surgery.work_ids
                ):
                    raise WorkflowError("Open this surgery in its original scene.")
            else:
                row = self.discipline._row(c, identity)
                if self.discipline_source(c, row)[0] != root or row["owner_id"] != str(
                    viewer.user_id
                ):
                    raise WorkflowError(
                        "Only the assigned account may answer this discipline work."
                    )
        if specialty:
            try:
                return self.followups.perform(viewer, key, data)
            except (KeyError, IndexError, AttributeError) as error:
                raise ValueError("Choose the current follow-up fields.") from error
        if step == "allow_locked_tag":
            return self.permissions.grant(
                viewer, key, identity, data.get("expected"), answer is True
            )
        if step == "resolve_locked_tag":
            return self.game.respond(
                viewer,
                key,
                identity,
                data["revision"],
                ChoiceAnswer.model_validate_json(json.dumps(answer)),
            )
        if step in (
            *DISCIPLINE_STEPS,
            "surgery_plan",
            "surgery_responses",
            "surgery_ready",
            "answer_punishment_consult",
        ):
            return self.controls.perform(
                viewer, key, {k: v for k, v in data.items() if k != "root"}
            )
        if step not in (
            "apply_scene_punishment",
            "request_punishment_consult",
            "apply_approved_punishment",
        ):
            raise ValueError("Choose an available discipline step.")
        if type(data.get("work_revision")) is not int or not isinstance(answer, dict):
            raise ValueError("Reopen the current discipline work.")
        if step == "apply_approved_punishment":
            current = self.discipline.get(viewer, identity)
            consent = current["consultation"]
            if not consent or not consent["approved"]:
                raise WorkflowError("The Handler must approve the exact proposal first.")
            answer = self.discipline.get(viewer, consent["id"])["proposal"]
        operation = (
            self.discipline.consult
            if step == "request_punishment_consult"
            else self.discipline.apply
        )
        return operation(
            viewer,
            key,
            identity,
            data["work_revision"],
            data["revision"],
            discipline_details(answer),
        )

    def recover_followup(self, viewer, key, identity, root, revision, answer):
        resume = answer.get("action") if isinstance(answer, dict) else None
        if not isinstance(resume, str) or not self.followups:
            raise ValueError("Reopen the assigned follow-up.")

        def authorize(c):
            self.discipline.missions.access.authorize(c, viewer, "plays")
            self.game.unpaused(c)

        def recover(c):
            work = _latest_work(c, self.game)
            source = self.followup_source(
                c, identity, resume, load_state(c, self.game.store.campaign_id), work
            )
            if (
                source is None
                or source[0] != root
                or not any(
                    card["id"] == identity
                    and card["action"] == resume
                    and card["revision"] == revision
                    for card in self.followups.view(viewer)
                )
            ):
                raise WorkflowError("Reopen your current assigned follow-up.")
            action, _ = self.source(c, root)
            if legacy := self.legacy_origin(c, action, work):
                discipline_finished(self.game, c, viewer, key, legacy)
            return {"id": identity, "state": "ready"}

        return self.game.store._write(
            viewer,
            key,
            "activity.scene_followup_recovered",
            {"id": identity, "root": root, "revision": revision, "action": resume},
            recover,
            auto_audit=False,
            authorize=authorize,
        )
