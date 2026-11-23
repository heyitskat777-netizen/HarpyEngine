"""Activity controls for the original participants in a Handler's Punishment."""

import json

from girlframe.engine.campaign_opening import RESTRICTED_PUNISHMENTS
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_lobotomy_state import OPTIONS, Plan
from girlframe.engine.m3_punishments import KINDS, Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m2_state import load_state
from girlframe.services.m3_lobotomy import LobotomyService
from girlframe.services.m3_punishment_sources import LEGACY, recover
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_role_punishments import RolePunishmentService, _latest_work
from girlframe.services.onboarding import WorkflowError

FOLLOWUPS = {
    "punishment_helpless": "Review last Girl Asset loss",
    "punishment_frame_loss": "Review last Frame Asset loss",
    "punishment_paired_identity_heat": "Allocate your Paired Identity Heat",
    "punishment_ankou_feedback": "Resolve the assigned Ankou Feedback",
    "punishment_void_threshold_check": "Resolve the assigned Void threshold work",
}
DISCIPLINE_TITLES = {
    "mission_failure": "Mission debrief · Failure Punishment",
    "dog_mission_end": "Mission debrief · Dog's Punishment",
    "off_duty_handler": "Handler Off-Duty Punishment",
    "defeat_post_mission": "Defeat · Post-mission Punishment",
}
ACTIVITY_ROLE_CASES = frozenset({
    "handler_play", "enforcement_initiative", "dose_up", "vatgrown_doll", "prince", "show_dog",
    "easy_target",
})


class HandlerPunishments:
    def __init__(self, game):
        self.service = RolePunishmentService(game)
        self.discipline = PunishmentService(game.store)
        self.surgeries = LobotomyService(game.store)

    def view(self, viewer):
        cards = []
        with self.service.store.engine.connect() as connection:
            state = load_state(connection, self.service.store.campaign_id)
            cases = handler_cases(state)
            tasks = self.service._tasks(connection, viewer) if cases else []
            work_ids = {case.pc_work for case in cases.values() if case.pc_work}
            items = _latest_work(connection, self.service.game)
            work_ids.update(
                row["id"]
                for row in items.values()
                if row["kind"] == "punishment"
                and json.loads(row["body_json"]).get("reason") in DISCIPLINE_TITLES
            )
            work = [
                row
                for row in items.values()
                if row["state"] != "resolved"
                and (
                    row["kind"] == "punishment"
                    and row["id"] in work_ids
                    and json.loads(row["body_json"]).get("reason") in DISCIPLINE_TITLES
                    and not json.loads(row["body_json"]).get("lobotomy_id")
                    and str(viewer.user_id) in (row["owner_id"], row["subject_id"])
                    or row["kind"] in FOLLOWUPS
                    and row["owner_id"] == str(viewer.user_id)
                    and (
                        row["kind"] in LEGACY
                        or json.loads(row["body_json"]).get("source_work") in work_ids
                    )
                    or row["kind"] == "punishment_consult"
                    and row["owner_id"] == str(viewer.user_id)
                    and work_ids.intersection(
                        json.loads(row["body_json"]).get("work_versions", {})
                    )
                )
            ]
            surgery_ids = {
                surgery.id
                for surgery in state.lobotomies
                if set(surgery.work_ids).intersection(work_ids)
            }
            surgeries = (
                [
                    task["id"]
                    for task in self.surgeries._tasks(connection, viewer)
                    if task["id"] in surgery_ids
                ]
                if surgery_ids
                else []
            )
        for task in tasks:
            if task["state"] == "resolved" or task["id"] not in cases:
                continue
            data = self.service.get(viewer, task["id"])
            case = data["case"]
            instruction = case["instruction"]
            details = (
                Details.model_validate_json(instruction["details_json"])
                if instruction
                else None
            )
            action = None
            if task["actionable"] and not data["stale"]:
                if instruction is None:
                    action = "instruct"
                elif data["can_approve"]:
                    action = "approve"
                elif not case["scene_account"]:
                    action = "scene"
                elif data["can_attest"]:
                    action = "attest"
                else:
                    action = "execute"
            cards.append(
                {
                    "id": task["id"],
                    "revision": data["revision"],
                    "action": action,
                    "stale": data["stale"],
                    "instruction": KINDS[instruction["kind"]][0]
                    if instruction
                    else None,
                    "instruction_details": [
                        f"{label} · {text}"
                        for label, text in (
                            ("Tag", details.tag if details else ""),
                            ("Behavioural rule", details.regulation if details else ""),
                        )
                        if text
                    ],
                    "scene": case["scene_account"],
                    **({"role_case": True} if case["source_kind"] != "handler_play" else {}),
                    "forms": instruction_forms(
                        data["kinds"], data["pc_choices"], data["peers"]
                    )
                    if action == "instruct"
                    else [],
                }
            )
        for row in work:
            kind = row["kind"]
            if kind == "punishment":
                if card := self.discipline_card(viewer, row, state.handler):
                    cards.append(card)
            elif kind == "punishment_consult":
                detail = self.discipline.get(viewer, row["id"])
                cards.append(
                    {
                        "id": row["id"],
                        "revision": state.revision,
                        "work_revision": row["revision"],
                        "action": "answer_punishment_consult",
                        "instruction": "Moderate Punishment consultation",
                        "instruction_details": detail["summary"],
                        "consult_stale": detail["stale"],
                    }
                )
            else:
                cards.append(
                    {
                        "id": row["id"],
                        "revision": state.revision,
                        "work_revision": row["revision"],
                        "action": kind
                        if kind
                        in (
                            "punishment_helpless",
                            "punishment_frame_loss",
                            "punishment_paired_identity_heat",
                        )
                        else "recover_punishment_followup"
                        if kind in LEGACY
                        else None,
                        "instruction": FOLLOWUPS[kind],
                    }
                )
        for identity in surgeries:
            detail = self.surgeries.get(viewer, identity)
            cards.append(
                {
                    "id": identity,
                    "revision": detail["game_revision"],
                    "action": "surgery_" + detail["phase"],
                    "instruction": "Experimental surgery · " + detail["patient"],
                    "surgery": detail | {"options": OPTIONS},
                }
            )
        return cards

    def discipline_card(self, viewer, row, handler):
        detail = self.discipline.get(viewer, row["id"])
        owner = str(viewer.user_id) == row["owner_id"]
        delegated = row["owner_id"] != str(handler)
        scene = detail.get("context_scene")
        card = {
            "id": row["id"],
            "revision": detail["game_revision"],
            "work_revision": detail["revision"],
            "instruction": DISCIPLINE_TITLES[self.discipline._body(row)["reason"]],
            "action": None,
            "scene": scene["summary"] if scene else None,
        }
        if scene and viewer.user_id not in scene["acknowledgements"]:
            return card | {"action": "attest_punishment_scene"}
        if not owner:
            return None
        if delegated and not scene:
            return card | {"action": "propose_punishment_scene"}
        if scene and set(scene["acknowledgements"]) != set(scene["participants"]):
            return card
        consultation = detail["consultation"]
        if consultation:
            review = self.discipline.get(viewer, consultation["id"])
            if consultation["state"] != "resolved":
                return card
            if consultation["approved"] and not review["stale"]:
                return card | {
                    "action": "apply_approved_punishment",
                    "instruction_details": review["summary"],
                }
        choices = detail.get("choices")
        if not choices:
            return card
        choices = choices | {
            "pilots": [
                (uid, label)
                for uid, label in choices["pilots"]
                if uid not in (row["owner_id"], row["subject_id"])
            ]
        }
        kinds = [
            kind
            for kind, (_, severity) in KINDS.items()
            if (severity != "severe" or not delegated)
            and (not detail.get("narrative_limit") or kind not in RESTRICTED_PUNISHMENTS)
            and (
                detail["required_severity"] is None
                or detail["required_severity"] == severity
            )
        ]
        return card | {
            "action": "apply_off_duty_punishment",
            "forms": instruction_forms(kinds, choices, ()),
            "consult_moderate": delegated,
            "conditioning_phrases": detail.get("conditioning_phrases", ()),
        }

    def perform(self, viewer, key, data):
        if (
            data.keys() - {"work_revision"} != {"id", "revision", "action", "answer"}
            or not isinstance(data["id"], str)
            or type(data["revision"]) is not int
        ):
            raise ValueError("Choose a current Punishment step.")
        identity = data["id"]
        action, answer = data["action"], data["answer"]
        if not isinstance(action, str):
            raise TypeError("Choose a current Punishment step.")
        if action in FOLLOWUPS or action in (
            "recover_punishment_followup",
            "apply_off_duty_punishment",
            "apply_approved_punishment",
            "answer_punishment_consult",
            "propose_punishment_scene",
            "attest_punishment_scene",
            "request_punishment_consult",
        ):
            return self.perform_work(
                viewer,
                key,
                identity,
                data["revision"],
                data.get("work_revision"),
                action,
                answer,
            )
        if action in ("surgery_plan", "surgery_responses", "surgery_ready"):
            if action == "surgery_plan" and isinstance(answer, dict):
                return self.surgeries.prepare(
                    viewer,
                    key,
                    identity,
                    data["revision"],
                    Plan.model_validate_json(json.dumps(answer)),
                )
            if (
                action == "surgery_responses"
                and isinstance(answer, dict)
                and all(isinstance(value, str) for value in answer.values())
            ):
                return self.surgeries.respond(
                    viewer, key, identity, data["revision"], answer
                )
            if action == "surgery_ready" and answer is True:
                return self.surgeries.finish(viewer, key, identity)
            raise ValueError("Submit the current assigned surgery decision.")
        info = self.service.get(viewer, identity)
        if info["case"]["source_kind"] not in ACTIVITY_ROLE_CASES:
            raise WorkflowError("Open this Punishment from its original workflow.")
        if action == "instruct" and isinstance(answer, dict):
            counterpart = answer.get("counterpart")
            actor = None
            if counterpart is not None:
                actor = next(
                    (
                        row["ref"]
                        for row in info["peers"]
                        if row["token"] == counterpart
                    ),
                    None,
                )
                if actor is None:
                    raise ValueError("Choose the original Bond counterpart.")
            details = discipline_details(
                {k: v for k, v in answer.items() if k != "counterpart"}
            )
            fields = {
                "instruction": Instruction(
                    kind=details.kind,
                    details_json=details.model_dump_json(),
                    counterpart=ActorRef.model_validate(actor) if actor else None,
                )
            }
        elif (
            action == "scene"
            and isinstance(answer, str)
            and 1 <= len(answer.strip()) <= 1200
        ):
            fields = {"scene": answer}
        elif action in ("attest", "approve") and answer is True:
            fields = {action: True}
        elif (
            action == "execute"
            and isinstance(answer, str)
            and 1 <= len(answer.strip()) <= 1200
        ):
            fields = {"execute": True, "account": answer}
        else:
            raise ValueError("Use the fields for this Punishment step.")
        return self.service.change(viewer, key, identity, data["revision"], **fields)

    def perform_work(
        self, viewer, key, identity, revision, work_revision, action, answer
    ):
        if type(work_revision) is not int or not isinstance(answer, dict):
            raise ValueError("Reopen the assigned discipline work.")
        args = (viewer, key, identity, work_revision, revision)
        if action == "recover_punishment_followup" and not answer:
            return recover(self.discipline, *args)
        if (
            action == "answer_punishment_consult"
            and type(answer.get("approve")) is bool
        ):
            return self.discipline.answer_consultation(
                viewer, key, identity, work_revision, answer["approve"]
            )
        if action in (
            "apply_off_duty_punishment",
            "apply_approved_punishment",
            "propose_punishment_scene",
            "attest_punishment_scene",
            "request_punishment_consult",
        ):
            with self.discipline.store.engine.connect() as connection:
                row = self.discipline._row(connection, identity)
                if (
                    row["kind"] != "punishment"
                    or self.discipline._body(row).get("reason") not in DISCIPLINE_TITLES
                ):
                    raise WorkflowError("Open the original Punishment workflow.")
            if action == "propose_punishment_scene" and isinstance(
                answer.get("summary"), str
            ):
                return self.discipline.propose_scene(*args, answer["summary"])
            if action == "attest_punishment_scene" and not answer:
                return self.discipline.attest_scene(*args)
            if action == "apply_approved_punishment" and not answer:
                current = self.discipline.get(viewer, identity)
                consultation = current["consultation"]
                if not consultation or not consultation["approved"]:
                    raise WorkflowError(
                        "The designated Handler must approve the proposal first."
                    )
                answer = self.discipline.get(viewer, consultation["id"])["proposal"]
            phrase = answer.get("conditioning_phrase")
            if "conditioning_phrase" in answer:
                if action != "apply_off_duty_punishment" or not isinstance(phrase, str):
                    raise ValueError("Choose a phrase only for the original Trainer's Punishment.")
                answer = {key: value for key, value in answer.items() if key != "conditioning_phrase"}
            details = discipline_details(answer)
            if action == "request_punishment_consult":
                return self.discipline.consult(*args, details)
            if action in ("apply_off_duty_punishment", "apply_approved_punishment"):
                return self.discipline.apply(*args, details, conditioning_phrase=phrase)
        if (
            action == "punishment_helpless"
            and answer.keys() == {"inside_frame", "evidence"}
            and type(answer["inside_frame"]) is bool
        ):
            return self.discipline.resolve_helpless(*args, **answer)
        if action == "punishment_frame_loss" and answer.keys() == {
            "piloting",
            "in_battle",
            "evidence",
        }:
            return self.discipline.resolve_frame_loss(*args, **answer)
        if action == "punishment_paired_identity_heat" and answer.keys() == {"share"}:
            return self.discipline.split_paired_heat(*args, answer["share"])
        raise ValueError("Use the fields for this assigned discipline work.")


def discipline_details(values):
    values = values.copy()
    for field in ("bond_with", "delegate"):
        if (
            isinstance(value := values.get(field), str)
            and value.isascii()
            and value.isdecimal()
        ):
            values[field] = int(value)
    return Details.model_validate_json(json.dumps(values))


def handler_cases(state):
    return {
        case.id: case
        for case in state.role_punishments
        if case.source_kind in ACTIVITY_ROLE_CASES
    }


def instruction_forms(kinds, choices, peers):
    own = choices or {}
    forms = []

    def pick(key, label, options, count=1):
        return {"key": key, "label": label, "options": list(options), "count": count}

    def text(key, label, size):
        return {"key": key, "label": label, "size": size}

    def entities(key, label, rows, count=1):
        return pick(
            key,
            label,
            (
                (str(row["id"]), row.get("name", row.get("label", row["id"])))
                for row in rows
            ),
            count,
        )

    def add(kind, fields, suffix=""):
        forms.append(
            {
                "id": kind + (":" + suffix if suffix else ""),
                "kind": kind,
                "severity": KINDS[kind][1],
                "label": KINDS[kind][0] + (" · " + suffix if suffix else ""),
                "fields": fields,
                "available": all(
                    len(field["options"]) >= field["count"]
                    for field in fields
                    if "options" in field
                ),
            }
        )

    for kind in kinds:
        fields = []
        if kind == "passing_responsibility":
            fields.append(
                pick("delegate", "Pilot taking responsibility", own.get("pilots", ()))
            )
        elif kind == "sedation" and own.get("identities"):
            fields.append(
                entities(
                    "identities",
                    "Identities to mark",
                    own["identities"],
                    min(2, len(own["identities"])),
                )
            )
        elif kind in ("beating", "frame_disassembly", "compliance_surgery"):
            family = "frame" if kind == "frame_disassembly" else "girl"
            assets = [
                row
                for row in own.get("assets", ())
                if row["family"] == family and (kind != "beating" or not row["damaged"])
            ]
            fields.append(
                entities(
                    "asset",
                    "Affected Asset",
                    assets + (own.get("body_parts", []) if kind == "beating" else []),
                )
            )
            if kind == "compliance_surgery":
                fields.extend(
                    [
                        text("replacement_name", "Replacement Girl Asset name", 120),
                        text(
                            "replacement_description", "Replacement description", 1200
                        ),
                    ]
                )
        elif kind == "revoked_privileges":
            fields += [
                entities(
                    "requisition", "Held Requisition", own.get("requisitions", ())
                ),
                text("restoration", "Restoration condition", 1200),
            ]
        elif kind == "reduced_socialization":
            fields.append(
                pick("bond_with", "Bond to weaken", own.get("bonds", ()))
                if choices is not None
                else pick(
                    "counterpart",
                    "Original Bond counterpart",
                    ((row["token"], row["label"]) for row in peers),
                )
            )
        elif kind == "strict_regulations":
            fields += [
                text("regulation", "Behavioural rule", 1200),
                pick(
                    "disclosed",
                    "Inform the affected pilot?",
                    (("yes", "Inform"), ("no", "Conceal")),
                ),
            ]
        elif kind == "correctional_programming":
            identities = entities(
                "identities",
                "Ordinary Identity to remove",
                own.get("removable_identities", ()),
            )
            add(kind, [identities], "erase Identity")
            embrace = [entities("embrace_tag", "Tag to embrace", own.get("tags", ()))]
            add(
                kind,
                embrace + ([identities] if own.get("identity_cap_reached") else []),
                "embrace Tag",
            )
            continue
        if kind in ("quality_time", "beating"):
            fields.append(text("tag", "Inflicted Tag", 120))
        add(kind, fields)
    return forms
