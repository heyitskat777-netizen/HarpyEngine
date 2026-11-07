"""Owned discipline work, fixed-proposal Handler consultation and atomic effects."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_punishments as rules
from girlframe.engine.m3_off_duty import Scene
from girlframe.engine.rules_registry import Registry
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class PunishmentService:
    def __init__(self, store: OnboardingStore, registry: Registry | None = None):
        self.store = store
        self.missions = MissionService(store, registry)
        self.game = self.missions.game

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] not in (
            "punishment",
            "punishment_consult",
            "punishment_paired_identity_heat",
            "punishment_helpless",
            "punishment_frame_loss",
        ):
            raise WorkflowError("This discipline task is unavailable.")
        if row["kind"] == "punishment" and json.loads(row["body_json"]).get("return_source_work"):
            from girlframe.services.m3_debts import check_returned

            check_returned(c, self.store, dict(row))
        if (
            row["kind"] == "punishment"
            and json.loads(row["body_json"]).get("reason") == "janus_core_tag_removal"
        ):
            from girlframe.services.m3_janus_requisitions import prove_tag_removal

            prove_tag_removal(c, self.game, dict(row))
        if (
            row["kind"] == "punishment"
            and json.loads(row["body_json"]).get("reason") == "cute_uniform_rejection"
        ):
            from girlframe.services.m3_cute_uniforms import validate_punishment_work

            validate_punishment_work(self.game, c, load_state(c, self.store.campaign_id), dict(row))
        if (
            row["kind"] == "punishment"
            and json.loads(row["body_json"]).get("reason") == "gender_woman_no"
        ):
            from girlframe.services.m3_gender_designation import validate_punishment_work

            validate_punishment_work(self.game, c, load_state(c, self.store.campaign_id), dict(row))
        from girlframe.services.m3_intracadre_marriage import prove_allocation

        prove_allocation(self.game, c, load_state(c, self.store.campaign_id), dict(row))
        return dict(row)

    def _body(self, row: dict[str, Any]) -> dict[str, Any]:
        return dict(json.loads(row["body_json"]))

    def _view(self, c: Connection, viewer: GuildViewer, row: dict[str, Any]) -> None:
        self.game.authorize(c, viewer, game=False)
        permitted = {row["owner_id"], row["subject_id"]}
        if self._body(row).get("role_case"):
            from girlframe.services.m3_role_punishments import case_proof

            permitted.add(
                str(case_proof(c, self.game, self._body(row)["role_case"]).executor_controller)
            )
        if row["kind"] == "punishment_consult":
            permitted.add(str(self._body(row)["inflictor"]))
        if str(viewer.user_id) not in permitted:
            raise WorkflowError("This discipline task belongs to other participants.")

    def _actor(self, c: Connection, viewer: GuildViewer, row: dict[str, Any]) -> None:
        self._view(c, viewer, row)
        if row["owner_id"] != str(viewer.user_id):
            raise WorkflowError("Only the designated decision owner may submit this task.")
        state = load_state(c, self.store.campaign_id)
        if viewer.user_id == state.handler:
            HandlerService(self.store).authorize(c, viewer)
        elif str(viewer.user_id) not in state.sheets:
            raise WorkflowError("A current canonical Pilot or Handler is required.")

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
        *,
        execution: bool = False,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "discipline")
            self.game.unpaused(c)
            row = self._row(c, identity)
            if execution and self._body(row).get("role_case"):
                from girlframe.services.m3_role_punishments import pc_execution

                pc_execution(c, self.game, row, viewer)
            else:
                self._actor(c, viewer, row)

        try:

            def apply_with_continuation(c: Connection) -> dict[str, Any]:
                row = self._row(c, identity)
                result = operation(c)
                from girlframe.services.m3_beneath import discipline_finished

                discipline_finished(self.game, c, viewer, key, row)
                if self._body(row).get("role_case") or self._body(row).get("source_work"):
                    from girlframe.services.m3_role_punishments import synchronize

                    latest = c.scalar(
                        sa.select(t.events.c.id)
                        .where(
                            t.events.c.campaign_id == self.store.campaign_id,
                        )
                        .order_by(t.events.c.seq.desc())
                        .limit(1)
                    )
                    if latest:
                        synchronize(self.game, c, None, latest)
                return result

            return self.store._write(
                viewer,
                key,
                kind,
                payload,
                apply_with_continuation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValidationError:
            raise WorkflowError("Invalid discipline choices; reopen the current task.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _check(self, c: Connection, row: dict[str, Any], revision: int, game_revision: int) -> None:
        original = self._body(row).get("character")
        if (
            original
            and self.game.character_binding(
                c,
                load_state(c, self.store.campaign_id),
                int(row["subject_id"]),
                require_current_profile=False,
            )
            != original
        ):
            raise WorkflowError("STALE_CHARACTER: this consequence belongs to its original Girl.")
        if row["state"] == "resolved" or row["revision"] != revision:
            raise WorkflowError("STALE_WORK: reopen the current discipline task.")
        if load_state(c, self.store.campaign_id).revision != game_revision:
            raise WorkflowError("STALE_STATE: sheets or Status changed; review the task again.")
        actions = t.m2["m2_actions"]
        from girlframe.services.m3_beneath import discipline_action, lineage

        source_action = discipline_action(self.game, c, row)
        allowed = lineage(self.game, c, source_action) if source_action is not None else []
        if self._body(row).get("role_case"):
            from girlframe.services.m3_role_punishments import case_proof

            case = case_proof(c, self.game, self._body(row)["role_case"])
            if case.action:
                allowed.append(case.action)
            if case.source_kind == "compliance_virus":
                from girlframe.services.m3_compliance_virus import source as virus_source

                _, purge = virus_source(c, self.game, case.source_work or "")
                allowed.append(purge.operational_action)
                if purge.discovery_action:
                    allowed.extend(lineage(self.game, c, purge.discovery_action))
        if c.scalar(
            sa.select(actions.c.id)
            .where(
                actions.c.campaign_id == self.store.campaign_id,
                actions.c.state.not_in(("complete", "aborted")),
                actions.c.id.not_in(allowed),
            )
            .limit(1)
        ):
            raise WorkflowError("Finish the pending scene Play before applying mission discipline.")

    def _save(self, c: Connection, row: dict[str, Any], event: str, **values: Any) -> None:
        body = values.pop("body", self._body(row))
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{k: v for k, v in row.items() if k not in ("revision", "body_json", "event_id")},
                revision=row["revision"] + 1,
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
            )
            .values(**values)
        )

    def _offender(self, row: dict[str, Any]) -> tuple[str, str | None]:
        body = self._body(row)
        original = body.get("marriage_offender")
        return (
            (original["entity"], original["incarnation"])
            if original
            else (row["subject_id"], body.get("character"))
        )

    def _bundle(self, c: Connection, row: dict[str, Any]) -> list[dict[str, Any]]:
        if self._body(row).get("reason") in (
            "marriage_caught",
            "strict_regulations",
            "put_someone_beneath_you",
            "cute_uniform_rejection",
            "gender_woman_no",
            "privacy_death",
            "janus_core_tag_removal",
            "defeat_post_mission",
            "role_punishment",
        ):
            return [row]
        if row["off_duty_id"] is not None:
            if self._body(row).get("return_source_work") and self._body(row).get("reason") in (
                "mission_failure",
                "dog_mission_end",
            ):
                source = self._body(row)
                result = [
                    item
                    for item in OffDutyService(self.missions)._pending(c, row["off_duty_id"])
                    if item["kind"] == "punishment"
                    and item["subject_id"] == row["subject_id"]
                    and self._offender(item) == self._offender(row)
                    and item["owner_id"] == row["owner_id"]
                    and self._body(item).get("reason") in ("mission_failure", "dog_mission_end")
                    and self._body(item).get("original_mission") == source["original_mission"]
                    and self._body(item).get("return_proof", {}).get("return_event")
                    == source["return_proof"]["return_event"]
                ]
                from girlframe.services.m3_debts import check_returned

                for item in result:
                    check_returned(c, self.store, item)
                return result
            if self._body(row).get("reason") not in (
                "m2_play",
                "off_duty_handler",
                "strain_event",
                "void_observation",
            ):
                raise WorkflowError("This Off-Duty cause needs its source-specific resolver.")
            return [row]
        if self._body(row).get("reason") not in ("mission_failure", "dog_mission_end"):
            raise WorkflowError("This cause requires its own source-specific discipline resolver.")
        result = [
            x
            for x in self.missions._pending(c, row["mission_id"])
            if x["kind"] == "punishment"
            and x["subject_id"] == row["subject_id"]
            and self._offender(x) == self._offender(row)
            and self._body(x).get("reason") in ("mission_failure", "dog_mission_end")
        ]
        if not result or any(x["owner_id"] != row["owner_id"] for x in result):
            raise WorkflowError("Resolve conflicting discipline ownership before applying effects.")
        if any(
            self._body(x).get("reason") not in ("mission_failure", "dog_mission_end")
            for x in result
        ):
            raise WorkflowError("This cause requires its own source-specific discipline resolver.")
        return result

    def _context(self, c: Connection, row: dict[str, Any]) -> dict[str, Any]:
        policy = self.store.policy.owner_m3_rulings
        duplicate_labels = policy is not None and policy.identity_duplicate_labels == "distinct_ids"
        if row["off_duty_id"] is None:
            return {"off_duty": False, "allow_duplicate_labels": duplicate_labels}
        period = OffDutyService(self.missions)._get(c, row["off_duty_id"])
        if period.phase not in (
            "preparing",
            "active",
        ) or period.handler != self.missions._current_handler(c):
            raise WorkflowError("Recover the changed Off-Duty context before discipline.")
        if self._body(row).get("role_case"):
            from girlframe.services.m3_role_punishments import case_proof

            case = case_proof(c, self.game, self._body(row)["role_case"])
            if set(case.attendance) != {case.executor_controller, case.subject_controller}:
                raise WorkflowError("Finish the actual executor/subject on-screen scene first.")
            return dict(
                off_duty=True, off_duty_period=period.id, allow_duplicate_labels=duplicate_labels
            )
        people = {int(row["subject_id"]), int(row["owner_id"])}
        saved_scene = self._body(row).get("context_scene")
        witnessed = False
        if saved_scene is not None:
            proof = Scene.model_validate_json(json.dumps(saved_scene))
            witnessed = people == set(proof.participants) == set(proof.acknowledgements)
        handler_scene = period.handler_scene
        if handler_scene is not None and handler_scene.kind == "punish":
            witnessed |= (
                people <= set(handler_scene.participants) == set(handler_scene.acknowledgements)
            )
        # Before the result is known, require actual on-screen proof rather than
        # speculating that a future roll will allow an off-screen Punishment.
        progress = period.progress.get(row["subject_id"])
        if progress is not None and progress.scene is not None:
            scene = progress.scene
            witnessed |= people <= set(scene.participants) == set(scene.acknowledgements)
        unknown_or_harsh = (
            progress is None
            or progress.roll is None
            or progress.roll.stage != "choices"
            or (progress.roll.source == "status" and progress.roll.total <= 7)
        )
        if unknown_or_harsh and not witnessed:
            raise WorkflowError(
                "Complete an on-screen Punishment scene with subject and inflictor first."
            )
        return {
            "off_duty": True,
            "off_duty_period": period.id,
            "allow_duplicate_labels": duplicate_labels,
        }

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            self._view(c, viewer, row)
            state = load_state(c, self.store.campaign_id)
            subject = int(row["subject_id"])
            sheet = state.sheets.get(str(subject))
            body = self._body(row)
            role_case_id = body.get("role_case")
            callsign = sheet.callsign if sheet else "Pilot"
            original_character = body.get("character")
            if original_character and (sheet is None or sheet.character_id != original_character):
                from girlframe.engine.m3_actor_state import ActorRef
                from girlframe.engine.m3_careers import archive_for, original_sheet

                original = ActorRef(
                    kind="pilot", entity=str(subject), incarnation=original_character
                )
                if archive_for(state, original) is not None:
                    callsign = original_sheet(state, original).callsign
            result: dict[str, Any] = {
                k: row[k]
                for k in (
                    "id",
                    "revision",
                    "kind",
                    "state",
                    "owner_id",
                    "subject_id",
                )
            }
            result.update(game_revision=state.revision, callsign=callsign)
            if role_case_id:
                result["role_case"] = role_case_id
            if body.get("lobotomy_id"):
                result["lobotomy_id"] = body["lobotomy_id"]
            if row["off_duty_id"] is not None and row["kind"] == "punishment":
                result["off_duty_id"] = row["off_duty_id"]
                result["context_scene"] = body.get("context_scene")
            if row["kind"] == "punishment_consult":
                proposal = dict(body["proposal"])
                if (
                    proposal["kind"] == "strict_regulations"
                    and not proposal.get("disclosed", True)
                    and viewer.user_id not in (body["inflictor"], state.handler)
                ):
                    proposal["regulation"] = "Concealed behavioural rule"
                result["proposal"] = proposal
                result["inflictor"] = body["inflictor"]
                result["stale"] = body["game_revision"] != state.revision
                labels = {x.id: x.name for x in sheet.identities + sheet.assets} if sheet else {}
                if sheet:
                    labels.update({x.id: x.label for x in sheet.tags})
                result["summary"] = [rules.KINDS[proposal["kind"]][0]] + [
                    key.replace("_", " ")
                    + ": "
                    + str(
                        [labels.get(x, x) for x in value]
                        if isinstance(value, list)
                        else labels.get(str(value), value)
                    )
                    for key, value in proposal.items()
                    if key != "kind"
                    and (value or (key == "disclosed" and proposal["kind"] == "strict_regulations"))
                    and (key != "disclosed" or proposal["kind"] == "strict_regulations")
                ]
            if row["kind"] == "punishment" and row["state"] != "resolved":
                bundle = self._bundle(c, row)
                result["causes"] = [self._body(x)["reason"] for x in bundle]
                result["required_severity"] = body.get("required_severity")
                result["consultation"] = None
                if body.get("consult_id"):
                    consultation = self._row(c, body["consult_id"])
                    result["consultation"] = {
                        "id": consultation["id"],
                        "state": consultation["state"],
                        "approved": self._body(consultation).get("approved", False),
                    }
                # Inflictor receives only fields necessary for the assigned choices.
                # No descriptions, notes, review snapshots, private NPCs or raw state.
                if row["owner_id"] == str(viewer.user_id) and sheet:
                    result["choices"] = {
                        "identities": [
                            {"id": x.id, "name": x.name, "slot": x.slot} for x in sheet.identities
                        ],
                        "removable_identities": [
                            {"id": x.id, "name": x.name, "slot": x.slot}
                            for x in sheet.identities
                            if not x.protected or (x.paired and subject == viewer.user_id)
                        ],
                        "assets": [
                            {"id": x.id, "name": x.name, "family": x.family, "damaged": x.damaged}
                            for x in sheet.assets
                        ],
                        "tags": [{"id": x.id, "name": x.label} for x in sheet.tags],
                        "bonds": [
                            (uid, other.callsign)
                            for uid, other in state.sheets.items()
                            if int(uid) != subject
                            and state.bonds.get(
                                ":".join(str(x) for x in sorted((subject, int(uid)))), 0
                            )
                        ],
                        "pilots": [
                            (uid, other.callsign)
                            for uid, other in state.sheets.items()
                            if HandlerService(self.store)._member(c, int(uid))
                        ],
                        "handler": state.handler,
                        "requisitions": [],
                        "identity_cap_reached": sum(
                            not x.protected or x.paired or x.am_limiter is not None
                            for x in sheet.identities
                        )
                        >= 4,
                    }
                    ruling = self.store.policy.owner_m3_rulings
                    if (
                        ruling
                        and ruling.privilege_restoration == "inflictor_condition_owner_restores"
                    ):
                        from girlframe.services.m3_privileges import choices

                        result["choices"]["requisitions"] = choices(c, self.game, state, subject)
                    if state.handler is not None and state.bonds.get(
                        ":".join(str(x) for x in sorted((subject, state.handler))), 0
                    ):
                        result["choices"]["bonds"].append((str(state.handler), "Handler"))
            return result

    def _approved(
        self,
        c: Connection,
        row: dict[str, Any],
        bundle: list[dict[str, Any]],
        details: rules.Details,
    ) -> bool:
        identity = self._body(row).get("consult_id")
        if not identity:
            return False
        consultation = self._row(c, identity)
        body = self._body(consultation)
        state = load_state(c, self.store.campaign_id)
        return bool(
            consultation["state"] == "resolved"
            and body.get("approved") is True
            and int(consultation["owner_id"]) == state.handler
            and body["game_revision"] == state.revision
            and body["proposal"] == details.model_dump(mode="json")
            and body["work_versions"] == {x["id"]: x["revision"] for x in bundle}
        )

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        details: rules.Details,
        *,
        execution_account: str | None = None,
    ) -> dict[str, Any]:
        details = rules.Details.model_validate_json(details.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, row, revision, game_revision)
            if row["kind"] != "punishment":
                raise WorkflowError("Choose the typed resolver for this required task.")
            severity = rules.validate(details)
            required_severity = self._body(row).get("required_severity")
            if required_severity is not None and severity != required_severity:
                raise WorkflowError(
                    "Apply the actual severity required by this source consequence."
                )
            bundle = self._bundle(c, row)
            state = load_state(c, self.store.campaign_id)
            role_case = None
            if self._body(row).get("role_case"):
                from girlframe.services.m3_role_punishments import pc_execution

                role_case = pc_execution(c, self.game, row, viewer, details)
                if execution_account is None or not execution_account.strip():
                    raise WorkflowError("Describe your actual execution of the exact instruction.")
            if self._body(row).get("lobotomy_id") and details.kind != "lobotomization":
                raise WorkflowError("Finish the actual pending surgery before changing Punishment.")
            if details.kind == "lobotomization":
                if details.surgery is None:
                    from girlframe.services.m3_lobotomy import start_in_transaction

                    self._context(c, row)
                    return start_in_transaction(c, self, viewer, key, row, bundle)
                surgery = next((x for x in state.lobotomies if x.id == details.surgery), None)
                if (
                    surgery is None
                    or surgery.phase != "ready"
                    or set(surgery.work_ids) != {x["id"] for x in bundle}
                    or any(self._body(x).get("lobotomy_id") != surgery.id for x in bundle)
                ):
                    raise WorkflowError(
                        "Resume the actual prepared surgery and patient's responses."
                    )
            if details.kind == "revoked_privileges":
                from girlframe.services.m3_privileges import choices

                ruling = self.store.policy.owner_m3_rulings
                if (
                    ruling is None
                    or ruling.privilege_restoration != "inflictor_condition_owner_restores"
                ):
                    raise WorkflowError(
                        "UNRESOLVED_RULING: record temporary restoration ownership."
                    )
                if details.requisition not in {
                    x["id"] for x in choices(c, self.game, state, int(row["subject_id"]))
                }:
                    raise WorkflowError("Choose an actual held Requisition from the current menu.")
            if details.kind == "passing_responsibility":
                target = details.delegate
                if (
                    target is None
                    or str(target) not in state.sheets
                    or not HandlerService(self.store)._member(c, target)
                ):
                    raise WorkflowError("Delegate to a current active Pilot.")
                if target == viewer.user_id:
                    raise WorkflowError("You already own this task; choose its Punishment instead.")
                event = self.game.event(
                    c,
                    viewer.user_id,
                    key,
                    "m3.punishment_delegated",
                    work_id=identity,
                    cause_count=len(bundle),
                )
                for item in bundle:
                    body = self._body(item)
                    body.pop("context_scene", None)
                    consultation_id = body.pop("consult_id", None)
                    if consultation_id:
                        consultation = self._row(c, consultation_id)
                        if consultation["state"] != "resolved":
                            self._save(
                                c,
                                consultation,
                                event,
                                state="resolved",
                                body=self._body(consultation)
                                | {"approved": False, "superseded": True},
                            )
                    if body.get("reason") in (
                        "put_someone_beneath_you",
                        "cute_uniform_rejection",
                        "gender_woman_no",
                    ):
                        body["discipline_owner_character"] = self.game.character_binding(
                            c, state, target, require_current_profile=False
                        )
                    self._save(c, item, event, owner_id=str(target), body=body)
                return {"id": identity, "state": "delegated", "cause_count": len(bundle)}
            inflictor = int(role_case.executor.entity) if role_case is not None else viewer.user_id
            if details.kind in (
                "beating",
                "compliance_surgery",
                "lobotomization",
                "frame_disassembly",
            ):
                from girlframe.engine.m3_actor_bonds import current_ref as harm_original
                from girlframe.engine.m3_am import require_harm

                actual_inflictor = (
                    role_case.executor
                    if role_case is not None
                    else (
                        harm_original(state, inflictor)
                        if str(inflictor) in state.sheets and inflictor != state.handler
                        else None
                    )
                )
                require_harm(state, actual_inflictor, harm_original(state, int(row["subject_id"])))
            consulted = bool(role_case and role_case.handler_approval_event) or self._approved(
                c, row, bundle, details
            )
            if severity == "moderate" and inflictor != state.handler and not consulted:
                raise WorkflowError(
                    "HANDLER_CONSULT_REQUIRED: submit this exact proposal for Handler "
                    "consultation first."
                )
            event_id = str(uuid4())
            character_ids = {
                uid: self.game.character_binding(c, state, uid, require_current_profile=False)
                for uid in {int(row["subject_id"]), inflictor}
                if uid != state.handler
            }
            for item in bundle:
                source = self._body(item).get("obligation_id")
                if source is not None:
                    debt = next(
                        (
                            x
                            for x in state.obligations
                            if x.id == source
                            and x.owner == int(self._offender(item)[0])
                            and x.kind == "punishment"
                            and x.state == "pending"
                        ),
                        None,
                    )
                    if debt is None:
                        raise WorkflowError(
                            "The original discipline debt changed; recover it explicitly."
                        )
                    debt.state = "fulfilled"
            result = rules.apply(
                state,
                int(row["subject_id"]),
                inflictor,
                details,
                entity_id=str(uuid4()),
                **self._context(c, row),
                handler_consulted=consulted,
                source_event=event_id,
                character_ids=character_ids,
                profile_context={
                    int(row["subject_id"]): c.execute(
                        sa.select(
                            t.characters.c.id,
                            t.characters.c.revision,
                        ).where(
                            t.characters.c.campaign_id == self.store.campaign_id,
                            t.characters.c.user_id == row["subject_id"],
                        )
                    )
                    .one()
                    ._tuple()
                },
            )
            if role_case is not None:
                from girlframe.services.m3_role_punishments import mark_pc_effect

                mark_pc_effect(result.state, role_case, event_id, execution_account or "")
            if details.kind == "beating":
                from girlframe.engine.m3_actor_bonds import current_ref
                from girlframe.engine.m3_appearance_matrix import record_damage
                from girlframe.engine.m3_handler_consequences import active_handler
                from girlframe.services.m3_beneath import discipline_action

                source_action = discipline_action(self.game, c, row)
                scene = row.get("scene_id") or (
                    self.game.action(c, source_action)["scene_id"] if source_action else None
                )
                damager = (
                    role_case.executor
                    if role_case
                    else (
                        active_handler(state)
                        if inflictor == state.handler
                        else current_ref(state, inflictor)
                    )
                )
                record_damage(
                    state,
                    result.state,
                    damager=damager,
                    target=current_ref(state, int(row["subject_id"])),
                    identity=details.asset,
                    scene=scene,
                    event=event_id,
                    action=source_action,
                    work=identity,
                    occurrence="beating:" + identity,
                )
            observation_period = None
            if self._body(row).get("reason") == "void_observation":
                from girlframe.services.m3_observation import discipline_applied

                periods = OffDutyService(self.missions)
                observation_period = discipline_applied(
                    periods._get(c, row["off_duty_id"]),
                    result.state,
                    int(row["subject_id"]),
                    self._body(row)["origin_outcome"],
                    event_id,
                )
            renamed_profile = None
            if details.kind == "lobotomization":
                from girlframe.services.m3_lobotomy import rename_profile

                assert details.surgery is not None
                renamed_profile = rename_profile(c, self.store, result.state, details.surgery)
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.punishment_applied",
                result.state,
                event_id=event_id,
                work_id=identity,
                punishment=details.kind,
                cause_count=len(bundle),
            )
            if renamed_profile is not None:
                from girlframe.services.m3_lobotomy import save_name_snapshot

                save_name_snapshot(c, self.store, renamed_profile, event)
            from girlframe.services.m3_privileges import suspend_benefits

            suspend_benefits(c, self.store, result.state, event)
            if observation_period is not None:
                OffDutyService(self.missions)._save(c, observation_period, event)
            for item in bundle:
                body = self._body(item) | {
                    "punishment": details.model_dump(mode="json"),
                    "applied_event": event,
                    "character": character_ids[int(row["subject_id"])],
                }
                self._save(c, item, event, state="resolved", body=body)
                if body.get("reason") == "cute_uniform_rejection":
                    from girlframe.services.m3_cute_uniforms import complete_punishment

                    complete_punishment(self.game, c, item, event)
                if body.get("reason") == "gender_woman_no":
                    from girlframe.services.m3_gender_designation import complete_punishment

                    complete_punishment(self.game, c, item, event)
                consultation_id = body.get("consult_id")
                if consultation_id:
                    consultation = self._row(c, consultation_id)
                    if consultation["state"] != "resolved":
                        self._save(
                            c,
                            consultation,
                            event,
                            state="resolved",
                            body=self._body(consultation) | {"approved": False, "superseded": True},
                        )
            for followup in result.followups:
                related(
                    c,
                    self.store,
                    row,
                    str(uuid4()),
                    int(state.handler)
                    if followup.kind in ("helpless", "frame_loss") and state.handler
                    else followup.owner,
                    followup.owner,
                    "punishment_" + followup.kind,
                    followup.model_dump(mode="json") | {"immediate": True, "source_work": identity},
                    event,
                )
            if (
                row["off_duty_id"] is not None
                and self._body(row).get("reason") == "off_duty_handler"
            ):
                periods = OffDutyService(self.missions)
                period = periods._get(c, row["off_duty_id"])
                scene = period.handler_scene
                if (
                    period.handler_work == identity
                    and scene is not None
                    and set(scene.participants) == set(scene.acknowledgements)
                ):
                    for item in periods._pending(c, period.id):
                        if item["kind"] == "off_duty_handler_scene":
                            self._save(
                                c,
                                item,
                                event,
                                state="resolved",
                                body=self._body(item)
                                | {"punishment_work": identity, "applied_event": event},
                            )
            if details.kind in ("execution", "indefinite_imprisonment"):
                from girlframe.services.m3_careers import synchronize_end

                ending = next(
                    x
                    for x in result.state.career_archives
                    if x.source_event == event and x.actor.entity == row["subject_id"]
                )
                synchronize_end(c, self.game, ending)
            return {
                "id": identity,
                "state": "resolved",
                "cause_count": len(bundle),
                "followups": len(result.followups),
            }

        return self._write(
            viewer,
            key,
            identity,
            "m3.punishment_apply",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "details": details.model_dump(mode="json"),
                "execution_account": execution_account,
            },
            operation,
            execution=True,
        )

    def resolve_helpless(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        *,
        inside_frame: bool,
        evidence: str,
    ) -> dict[str, Any]:
        if not evidence.strip() or len(evidence) > 1200:
            raise WorkflowError("Record the factual Frame context in 1–1200 characters.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            HandlerService(self.store).authorize(c, viewer)
            self._check(c, row, revision, game_revision)
            if row["kind"] != "punishment_helpless":
                raise WorkflowError("This task is not a last-Girl-Asset context review.")
            body = self._body(row)
            from girlframe.engine.m2 import AssetState, GameState
            from girlframe.engine.m3_actor_bonds import current_ref
            from girlframe.engine.m3_actor_state import ActorRef

            history = t.m2["m2_state_history"]
            first = (
                c.execute(
                    sa.select(t.m3["m3_required_work"]).where(
                        t.m3["m3_required_work"].c.campaign_id == self.store.campaign_id,
                        t.m3["m3_required_work"].c.id == identity,
                        t.m3["m3_required_work"].c.revision == 1,
                    )
                )
                .mappings()
                .one()
            )
            source_body = c.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == first["event_id"],
                )
            )
            original = GameState.model_validate_json(source_body) if source_body else None
            subject = int(row["subject_id"])
            saved_sheet = original.sheets.get(str(subject)) if original else None
            actual = load_state(c, self.store.campaign_id)
            if (
                saved_sheet is None
                or str(subject) not in actual.sheets
                or (saved_sheet.character_id != actual.sheets[str(subject)].character_id)
            ):
                raise WorkflowError("Recover the original last-Girl-Asset source and character.")
            assert original is not None
            actor = ActorRef(
                kind="pilot", entity=str(subject), incarnation=saved_sheet.character_id
            )
            placement = next((x for x in original.placements if x.actor == actor), None)
            if placement is not None and (placement.mode != "outside_frame") != inside_frame:
                raise WorkflowError("Use the actual source body's inside/outside Frame facts.")
            foe = current_ref(original, int(body["details"]["inflictor"]))
            removal_proven = False
            lost = body["details"].get("removed_asset")
            if lost:
                proof = next(
                    (
                        x
                        for x in original.obligations
                        if x.kind == "revoked_requisition"
                        and x.details.get("source_event") == first["event_id"]
                        and x.target == subject
                        and "asset" in x.details
                        and AssetState.model_validate_json(x.details["asset"]).id == lost
                        and AssetState.model_validate_json(x.details["asset"]).family == "girl"
                    ),
                    None,
                )
                source_kind = c.scalar(
                    sa.select(t.events.c.kind).where(
                        t.events.c.id == first["event_id"],
                        t.events.c.campaign_id == self.store.campaign_id,
                    )
                )
                removal_proven = (
                    proof is not None
                    and source_kind == "m3.punishment_applied"
                    and body["details"].get("removal_source") == first["event_id"]
                    and not any(x.id == lost for x in saved_sheet.assets)
                )
                if not removal_proven:
                    raise WorkflowError("Recover the actual source-proved Girl Asset removal.")
            context_event = str(uuid4())
            updated = rules.last_girl_asset_context(
                load_state(c, self.store.campaign_id),
                int(row["subject_id"]),
                int(body["details"]["inflictor"]),
                inside_frame=inside_frame,
                source_event=context_event,
                foe=foe,
                removal_proven=removal_proven,
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.last_girl_asset_frame_context_resolved",
                updated,
                event_id=context_event,
                work_id=identity,
            )
            self._save(
                c,
                row,
                event,
                state="resolved",
                body=body | {"inside_frame": inside_frame, "evidence": evidence.strip()},
            )
            return {"id": identity, "state": "resolved", "helpless": not inside_frame}

        return self._write(
            viewer,
            key,
            identity,
            "m3.beating_frame_context_resolved",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "inside_frame": inside_frame,
                "evidence": evidence,
            },
            operation,
        )

    def resolve_frame_loss(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        *,
        piloting: bool,
        in_battle: bool,
        evidence: str,
    ) -> dict[str, Any]:
        if (
            type(piloting) is not bool
            or type(in_battle) is not bool
            or not evidence.strip()
            or len(evidence) > 1200
        ):
            raise WorkflowError("Record the actual battle and Frame context with factual evidence.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            HandlerService(self.store).authorize(c, viewer)
            self._check(c, row, revision, game_revision)
            if row["kind"] != "punishment_frame_loss":
                raise WorkflowError("This task is not a last-Frame-Asset review.")
            body = self._body(row)
            facts = body["details"]
            subject = int(row["subject_id"])
            state = load_state(c, self.store.campaign_id)
            character = self.game.character_binding(
                c, state, subject, require_current_profile=False
            )
            sheet = state.sheets[str(subject)]
            frame = sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + character
            if (
                character != facts["character"]
                or frame != facts["frame"]
                or any(x.family == "frame" and not x.damaged for x in sheet.assets)
            ):
                raise WorkflowError("STALE_FRAME_LOSS: recover the original Frame and resources.")
            if "piloting" in facts and facts["piloting"] != str(piloting):
                raise WorkflowError(
                    "The source placement already records the actual Frame context."
                )
            needs_defeat = piloting and in_battle
            state.facts.append(
                dict(
                    kind="punishment_frame_loss_context",
                    work=identity,
                    character=character,
                    frame=frame,
                    piloting=str(piloting),
                    in_battle=str(in_battle),
                    evidence=evidence.strip(),
                )
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frame_loss_context_resolved",
                state,
                work_id=identity,
                defeat_required=needs_defeat,
            )
            self._save(
                c,
                row,
                event,
                state="resolved",
                body=body
                | dict(
                    piloting=piloting,
                    in_battle=in_battle,
                    evidence=evidence.strip(),
                    defeat_required=needs_defeat,
                ),
            )
            if needs_defeat:
                related(
                    c,
                    self.store,
                    row,
                    str(uuid4()),
                    subject,
                    subject,
                    "defeat",
                    dict(
                        source_work=identity,
                        source_pdf=29,
                        immediate=True,
                        character=character,
                        frame=frame,
                        trigger="last_frame_asset_removed",
                    ),
                    event,
                )
            return dict(id=identity, state="resolved", defeat_required=needs_defeat)

        return self._write(
            viewer,
            key,
            identity,
            "m3.frame_loss_context_resolved",
            dict(
                id=identity,
                revision=revision,
                game_revision=game_revision,
                piloting=piloting,
                in_battle=in_battle,
                evidence=evidence,
            ),
            operation,
        )

    def split_paired_heat(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        share: int,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, row, revision, game_revision)
            if (
                row["kind"] != "punishment_paired_identity_heat"
                or type(share) is not int
                or not 0 <= share <= 5
            ):
                raise WorkflowError(
                    "Only the Paired Identity's owner chooses a zero-to-five Heat share."
                )
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet is None or row["subject_id"] != str(viewer.user_id):
                raise WorkflowError("The Paired Identity belongs to another Pilot.")
            pair = state.sheets.get(str(sheet.pair))
            if share and (pair is None or pair.owner == viewer.user_id):
                raise WorkflowError("Resolve the current Pair before sharing Heat.")
            sheet.heat += 5 - share
            sheet.revision += 1
            if share and pair is not None:
                pair.heat += share
                pair.revision += 1
            event = self.game.event(
                c, viewer.user_id, key, "m3.paired_identity_heat_split", state, work_id=identity
            )
            self._save(c, row, event, state="resolved", body=self._body(row) | {"share": share})
            return {"id": identity, "state": "resolved"}

        return self._write(
            viewer,
            key,
            identity,
            "m3.paired_identity_heat_split",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "share": share,
            },
            operation,
        )

    def consult(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        details: rules.Details,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, row, revision, game_revision)
            state = load_state(c, self.store.campaign_id)
            if (
                row["kind"] != "punishment"
                or rules.validate(details) != "moderate"
                or viewer.user_id == state.handler
            ):
                raise WorkflowError(
                    "Only a designated Pilot inflictor needs Moderate consultation."
                )
            if state.handler is None:
                raise WorkflowError("Appoint a Handler first.")
            # Validate mechanical legality before asking the Handler to review it.
            rules.apply(
                state,
                int(row["subject_id"]),
                viewer.user_id,
                details,
                entity_id="consultation-preview",
                **self._context(c, row),
                handler_consulted=True,
                source_event="consultation-preview",
                character_ids={
                    uid: self.game.character_binding(c, state, uid, require_current_profile=False)
                    for uid in {int(row["subject_id"]), viewer.user_id}
                    if uid != state.handler
                },
            )
            bundle = self._bundle(c, row)
            previous = self._body(row).get("consult_id")
            if previous and self._row(c, previous)["state"] != "resolved":
                raise WorkflowError("A Handler consultation is already pending; reopen it.")
            consultation_id = str(uuid4())
            event = self.game.event(
                c, viewer.user_id, key, "m3.punishment_consult_requested", work_id=identity
            )
            body = {
                "proposal": details.model_dump(mode="json"),
                "inflictor": viewer.user_id,
                "game_revision": state.revision,
                "work_versions": {x["id"]: x["revision"] + 1 for x in bundle},
            }
            related(
                c,
                self.store,
                row,
                consultation_id,
                state.handler,
                int(row["subject_id"]),
                "punishment_consult",
                body,
                event,
            )
            for item in bundle:
                self._save(c, item, event, body=self._body(item) | {"consult_id": consultation_id})
            return {"id": consultation_id, "state": "pending"}

        return self._write(
            viewer,
            key,
            identity,
            "m3.punishment_consult",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "details": details.model_dump(mode="json"),
            },
            operation,
        )

    def answer_consultation(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, approve: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            HandlerService(self.store).authorize(c, viewer)
            if (
                row["kind"] != "punishment_consult"
                or row["state"] == "resolved"
                or row["revision"] != revision
                or type(approve) is not bool
            ):
                raise WorkflowError("STALE_WORK: reopen the current consultation.")
            body = self._body(row)
            if approve and load_state(c, self.store.campaign_id).revision != body["game_revision"]:
                raise WorkflowError(
                    "STALE_STATE: decline this stale proposal and request a fresh review."
                )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.punishment_consult_answered",
                work_id=identity,
                approved=approve,
            )
            self._save(c, row, event, state="resolved", body=body | {"approved": approve})
            return {"id": identity, "state": "resolved", "approved": approve}

        return self._write(
            viewer,
            key,
            identity,
            "m3.punishment_consult_answer",
            {"id": identity, "revision": revision, "approve": approve},
            operation,
        )

    def propose_scene(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        summary: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, row, revision, game_revision)
            if (
                row["kind"] != "punishment"
                or row["off_duty_id"] is None
                or self._body(row).get("context_scene")
            ):
                raise WorkflowError("Set one actual scene for this pending Off-Duty Punishment.")
            people = tuple(dict.fromkeys((int(row["owner_id"]), int(row["subject_id"]))))
            scene = Scene(kind="punishment", participants=people, summary=summary)
            event = self.game.event(
                c, viewer.user_id, key, "m3.punishment_scene_set", work_id=identity
            )
            self._save(
                c,
                row,
                event,
                body=self._body(row) | {"context_scene": scene.model_dump(mode="json")},
            )
            return {"id": identity, "revision": revision + 1, "state": "scene_pending"}

        return self._write(
            viewer,
            key,
            identity,
            "m3.punishment_scene_set",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "summary": summary,
            },
            operation,
        )

    def attest_scene(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "discipline")
            self.game.unpaused(c)
            row = self._row(c, identity)
            self._view(c, viewer, row)
            if str(viewer.user_id) not in (row["owner_id"], row["subject_id"]):
                raise WorkflowError("Only an actual participant confirms this Punishment scene.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, row, revision, game_revision)
            body = self._body(row)
            if (
                row["kind"] != "punishment"
                or row["off_duty_id"] is None
                or not body.get("context_scene")
            ):
                raise WorkflowError("Resume an actual pending Punishment scene.")
            scene = Scene.model_validate_json(json.dumps(body["context_scene"]))
            if viewer.user_id not in scene.participants or viewer.user_id in scene.acknowledgements:
                raise WorkflowError(
                    "Each participant confirms the played scene for themselves once."
                )
            updated = Scene.model_validate_json(
                scene.model_copy(
                    update={"acknowledgements": scene.acknowledgements + (viewer.user_id,)}
                ).model_dump_json()
            )
            event = self.game.event(
                c, viewer.user_id, key, "m3.punishment_scene_attested", work_id=identity
            )
            self._save(
                c, row, event, body=body | {"context_scene": updated.model_dump(mode="json")}
            )
            return {"id": identity, "revision": revision + 1, "state": "scene_attested"}

        return self.store._write(
            viewer,
            key,
            "m3.punishment_scene_attested",
            {"id": identity, "revision": revision, "game_revision": game_revision},
            operation,
            auto_audit=False,
            authorize=authorize,
        )
