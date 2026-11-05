"""Honest diceless operational roots acquire real chat pause before any purge effect."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_compliance_virus as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_compliance_virus_state import Purge, Strain
from girlframe.engine.m3_physical import original_placement
from girlframe.engine.m3_role_punishments import view
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_compliance_virus import (
    VirusService,
    _audit,
    _authority,
    _history,
    _resolve_work,
    source,
)
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def reserve(game: "GameService", c: Connection, state: GameState, value: Purge, label: str) -> None:
    current = game.lock(c, value.channel)
    if current and current["state"] != "released":
        raise WorkflowError("SCENE_BUSY: restore existing actual chat lock before this operation.")
    participants = sorted(
        set(
            [value.creator_controller, value.frame_controller, value.judge_controller]
            + ([value.target_controller] if value.target_controller else [])
        )
    )
    data = dict(
        play="compliance_virus",
        virus_purge=value.id,
        virus_initiator=value.creator.model_dump(mode="json"),
        participants=participants,
        handler=state.handler,
        label=label,
        receipt=None,
        modifiers=[],
        result={},
        choices={},
        method="DICELESS OPERATION; NO RNG; NO HEAT",
    )
    c.execute(
        t.m2["m2_actions"]
        .insert()
        .values(
            campaign_id=game.store.campaign_id,
            id=value.operational_action,
            actor_id=str(value.creator_controller),
            channel_id=str(value.channel),
            scene_id=value.scope.scene_id,
            parent_id=None,
            revision=1,
            state="acquiring",
            body_json=json.dumps(data, sort_keys=True),
        )
    )
    locks = t.m2["m2_locks"]
    values = dict(
        action_id=value.operational_action,
        state="acquiring",
        body_json="{}",
        lease_until=0,
        claim_token=None,
    )
    if current:
        c.execute(
            locks.update()
            .where(
                locks.c.campaign_id == game.store.campaign_id,
                locks.c.channel_id == str(value.channel),
            )
            .values(**values)
        )
    else:
        c.execute(
            locks.insert().values(
                campaign_id=game.store.campaign_id, channel_id=str(value.channel), **values
            )
        )


def held(game: "GameService", c: Connection, value: Purge) -> dict[str, Any]:
    action = game.action(c, value.operational_action)
    lock = game.lock(c, value.channel)
    if (
        action["data"].get("virus_purge") != value.id
        or int(action["channel_id"]) != value.channel
        or action["scene_id"] != value.scope.scene_id
        or action["parent_id"] is not None
        or lock is None
        or lock["action_id"] != action["id"]
        or lock["state"] != "held"
    ):
        raise WorkflowError("CHAT_NOT_HELD: acquire the actual original source lock before purge.")
    return action


def _clear(game: "GameService", c: Connection, value: Purge, event: str) -> dict[str, Any]:
    action = game.action(c, value.operational_action)
    table = t.m2["m2_choices"]
    for row in game.pending(c, action["id"]):
        body = json.loads(row["body_json"])
        if row["kind"] != "virus_purge_work" or body.get("purge") != value.id:
            raise WorkflowError("Finish only the actual matching source procedure choice.")
        c.execute(
            table.update()
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == row["id"])
            .values(
                state="completed_by_work",
                revision=row["revision"] + 1,
                body_json=json.dumps(body | dict(completed_by_purge=value.id, source_event=event)),
            )
        )
    return action


def advance(game: "GameService", c: Connection, value: Purge, event: str) -> None:
    if value.phase in ("complete", "ended"):
        return
    action = _clear(game, c, value, event)
    owner = (
        value.frame_controller
        if value.phase == "vacancy_proposal"
        else value.judge_controller
        if value.phase in ("contact_review", "vacancy_review", "punishment")
        else value.creator_controller
    )
    game.request(
        c,
        action,
        owner,
        "virus_purge_work",
        dict(purge=value.id, phase=value.phase, case_id=value.role_case),
    )
    game.save_action(c, action, state="awaiting_choices")


def finish(game: "GameService", c: Connection, value: Purge, event: str) -> None:
    action = game.action(c, value.operational_action)
    if action["state"] in ("complete", "aborted"):
        return
    if value.phase not in ("complete", "ended"):
        raise WorkflowError("Actual source effects and owned followups must finish before release.")
    action = _clear(game, c, value, event)
    action["state"] = "complete"
    action["data"]["result"].update(
        purge=value.id,
        actual_completion=event,
        original_ended=value.phase == "ended",
        method="PRINTED FIXED11 / NO ROLL"
        if value.kind == "frame" and value.role_case
        else "ACTUAL SOURCE DICELESS OPERATION",
    )
    game.save_action(c, action)
    game.queue(
        c,
        action,
        "outcome",
        dict(
            play=action["data"]["play"],
            callsign=action["data"]["label"],
            receipt=None,
            total=None,
            tier=None,
        ),
    )


def apply_frame(
    game: "GameService", c: Connection, state: GameState, value: Purge, event: str
) -> tuple[GameState, Purge]:
    from girlframe.services.m3_role_punishments import open_case, supported

    strain = rules.record(state, Strain, value.strain)
    people = rules.linked(state, strain.target)
    if len(people) != 1:
        raise WorkflowError(
            "Actual fixed11 effect needs exactly one source-proved linked original."
        )
    target = people[0][0]
    actor = view(state, target, profiles(c, game.store.campaign_id))
    if target != value.creator and not supported(
        state, target, value.creator, profiles(c, game.store.campaign_id)
    ):
        raise WorkflowError("Actual linked original needs a completed source Punishment port.")
    updated = value.model_copy(
        update=dict(
            target=target,
            target_controller=actor.controller,
            phase="punishment",
            effect_event=event,
            role_case=str(uuid4()),
            punishment_executor=value.creator,
            punishment_executor_frame=value.creator_frame,
            revision=value.revision + 1,
        )
    )
    changed = rules.frame_purge(state, updated, profiles(c, game.store.campaign_id))
    assert updated.role_case is not None
    changed, _ = open_case(
        changed,
        profiles(c, game.store.campaign_id),
        actor=value.creator,
        target=target,
        chooser=value.judge,
        source_kind="compliance_virus",
        action=None,
        source_work=value.id,
        source_event=event,
        identity=updated.role_case,
        chooser_controller=value.judge_controller,
        executor_controller=value.creator_controller,
    )
    return changed, updated


def prove_effect(game: "GameService", c: Connection, value: Purge) -> None:
    proof = rules.record(_history(c, game, value.effect_event), Purge, value.id)
    if (
        proof.kind != "frame"
        or proof.phase != "punishment"
        or proof.role_case != value.role_case
        or proof.operational_action != value.operational_action
        or proof.target != value.target
    ):
        raise WorkflowError(
            "Recover actual post-lock deterministic fixed11 source, not a dice label."
        )
    if value.vacancy_reviewed_event == value.effect_event:
        _audit(
            c,
            game,
            value.vacancy_proposed_event,
            value.frame_controller,
            "m3.virus_frame_occupancy_proposed",
        )
        _audit(
            c, game, value.effect_event, value.judge_controller, "m3.virus_frame_occupancy_reviewed"
        )
        if value.vacancy_kind != "owner_linked":
            raise WorkflowError("A vacant Frame cannot fabricate a linked Pilot.")
    else:
        _audit(c, game, value.effect_event, value.creator_controller, "m3.compliance_virus_effect")


def prove_vacancy(game: "GameService", c: Connection, value: Purge) -> None:
    if (
        value.vacancy_kind != "vacant"
        or value.target is not None
        or value.target_controller is not None
        or value.role_case is not None
        or not value.vacancy_proposed_event
        or not value.vacancy_reviewed_event
        or value.effect_event != value.vacancy_reviewed_event
        or value.completion_event != value.effect_event
    ):
        raise WorkflowError(
            "Actual vacant purge needs both real factual owners, without a fictional Pilot."
        )
    _audit(
        c,
        game,
        value.vacancy_proposed_event,
        value.frame_controller,
        "m3.virus_frame_occupancy_proposed",
    )
    _audit(
        c,
        game,
        value.vacancy_reviewed_event,
        value.judge_controller,
        "m3.virus_frame_occupancy_reviewed",
    )
    snapshot = _history(c, game, value.effect_event)
    actual = rules.record(snapshot, Purge, value.id)
    strain = rules.record(snapshot, Strain, value.strain)
    if (
        actual.phase != "complete"
        or actual.vacancy_kind != "vacant"
        or strain.purged_event != value.effect_event
        or rules.linked(snapshot, strain.target)
    ):
        raise WorkflowError(
            "A source label cannot replace actual confirmed vacancy and actual cure."
        )


class OperationService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def activate(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            action = self.game.action(c, identity)
            state, value = source(c, self.game, action["data"].get("virus_purge", ""))
            held(self.game, c, value)
            _authority(c, self.game, state, value)
            if (
                viewer.user_id != value.creator_controller
                or value.phase != "queued"
                or action["state"] not in ("ready_to_roll", "acquiring")
            ):
                raise WorkflowError(
                    "Only actual confirmed initiator starts this original operation once."
                )
            event = str(uuid4())
            if value.kind == "frame":
                people = rules.linked(state, rules.record(state, Strain, value.strain).target)
                if len(people) > 1:
                    raise WorkflowError(
                        "Recover contradictory actual linked bodies, without guessing."
                    )
                if people:
                    state, updated = apply_frame(self.game, c, state, value, event)
                else:
                    updated = value.model_copy(
                        update=dict(phase="vacancy_proposal", revision=value.revision + 1)
                    )
                    rules.put(state, updated)
            else:
                updated = value.model_copy(
                    update=dict(phase="contact_review", revision=value.revision + 1)
                )
                rules.put(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.compliance_virus_effect",
                state,
                event_id=event,
                purge=value.id,
                action_id=identity,
                method="printed_fixed11_no_roll"
                if updated.role_case
                else "owned_factual_procedure",
            )
            advance(self.game, c, updated, event)
            if updated.role_case:
                from girlframe.services.m3_role_punishments import synchronize

                synchronize(self.game, c, None, event)
            return dict(
                action_id=identity, state="awaiting_choices", receipt=None, method="diceless"
            )

        return VirusService(self.game)._write(
            viewer, key, "m3.compliance_virus_effect", dict(action_id=identity), operation
        )

    def cancel(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            from girlframe.services.m3_medical import MedicalService

            self.game.authorize(c, viewer, game=False)
            action = self.game.action(c, identity)
            _, value = source(c, self.game, action["data"].get("virus_purge", ""))
            staff = (
                viewer.is_administrator and self.store.policy.allow_guild_administrators
            ) or MedicalService(self.store)._handler(c)[0] == viewer.user_id
            if viewer.user_id != value.creator_controller and not staff:
                raise WorkflowError(
                    "Only source owner or configured actual staff cancels this operation."
                )

        def operation(c: Connection) -> dict[str, Any]:
            state, value = source(
                c, self.game, self.game.action(c, identity)["data"]["virus_purge"]
            )
            if (
                value.phase
                not in ("queued", "contact_review", "vacancy_proposal", "vacancy_review")
                or value.effect_event is not None
            ):
                raise WorkflowError(
                    "Actual purge effects and required Punishment cannot be waived by abort."
                )
            event = str(uuid4())
            updated = value.model_copy(
                update=dict(
                    phase="ended",
                    end_reason="cancelled_before_effect",
                    cancelled_by=viewer.user_id,
                    completion_event=event,
                    revision=value.revision + 1,
                )
            )
            rules.put(state, updated)
            action = self.game.action(c, identity)
            for row in self.game.pending(c, identity):
                choices = t.m2["m2_choices"]
                c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == self.store.campaign_id, choices.c.id == row["id"]
                    )
                    .values(state="cancelled_before_effect", revision=row["revision"] + 1)
                )
            self.game.save_action(c, action, state="aborted")
            locks = t.m2["m2_locks"]
            lock = self.game.lock(c, value.channel)
            if lock is None or lock["action_id"] != identity:
                raise WorkflowError("Recover original operational lock before cancelling it.")
            c.execute(
                locks.update()
                .where(
                    locks.c.campaign_id == self.store.campaign_id,
                    locks.c.channel_id == str(value.channel),
                )
                .values(state="releasing", claim_token=None, lease_until=0)
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.compliance_virus_cancelled",
                state,
                event_id=event,
                purge=value.id,
                action_id=identity,
            )
            _resolve_work(c, self.game, updated, event)
            return dict(action_id=identity, state="aborted")

        return self.store._write(
            viewer,
            key,
            "m3.compliance_virus_cancelled",
            dict(action_id=identity),
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def occupancy(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, choice: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = source(c, self.game, identity)
            _authority(c, self.game, state, value)
            held(self.game, c, value)
            if (
                value.revision != revision
                or value.phase not in ("vacancy_proposal", "vacancy_review")
                or not account.strip()
            ):
                raise WorkflowError("Use the actual original Frame occupancy source review.")
            if value.target_frame is None:
                raise WorkflowError("Actual source Frame is required for occupancy review.")
            event = str(uuid4())
            if value.phase == "vacancy_proposal":
                if viewer.user_id != value.frame_controller or choice not in (
                    "vacant",
                    "owner_linked",
                ):
                    raise WorkflowError(
                        "Only actual Frame owner records vacant or her actual own link."
                    )
                updated = value.model_copy(
                    update=dict(
                        phase="vacancy_review",
                        vacancy_kind=choice,
                        vacancy_proposed_event=event,
                        revision=value.revision + 1,
                    )
                )
                if choice == "owner_linked":
                    target = rules.frame_actor(state, value.target_frame)
                    actual = resolve(
                        state,
                        target,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    if (
                        target.kind != "pilot"
                        or actual.frame_instance != value.target_frame.instance
                        or actual.controller != viewer.user_id
                    ):
                        raise WorkflowError(
                            "Record actual original assigned-Frame Pilot facts, "
                            "not invented foreign control."
                        )
                rules.put(state, updated)
                kind = "m3.virus_frame_occupancy_proposed"
            else:
                if viewer.user_id != value.judge_controller or choice not in ("confirm", "reject"):
                    raise WorkflowError("Only original frozen judge reviews actual Frame facts.")
                _audit(
                    c,
                    self.game,
                    value.vacancy_proposed_event,
                    value.frame_controller,
                    "m3.virus_frame_occupancy_proposed",
                )
                if choice == "reject":
                    updated = value.model_copy(
                        update=dict(
                            phase="vacancy_proposal",
                            vacancy_kind=None,
                            vacancy_proposed_event=None,
                            vacancy_reviewed_event=None,
                            revision=value.revision + 1,
                        )
                    )
                    rules.put(state, updated)
                elif value.vacancy_kind == "owner_linked":
                    target = rules.frame_actor(state, value.target_frame)
                    actual = resolve(
                        state,
                        target,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    if (
                        actual.controller != value.frame_controller
                        or target.kind != "pilot"
                        or actual.frame_instance != value.target_frame.instance
                    ):
                        raise WorkflowError(
                            "No new body or different Frame inherits this current factual link."
                        )
                    current = next((x for x in state.placements if x.actor == target), None)
                    if current is not None and current.mode != "piloting":
                        raise WorkflowError(
                            "Actual known physical facts contradict claimed current link."
                        )
                    if current is None:
                        state, _ = original_placement(
                            state,
                            profiles(c, self.store.campaign_id),
                            target,
                            event,
                            account,
                            prior_event=value.source_event,
                            mode="piloting",
                        )
                    state = rules.spread(
                        state, profiles(c, self.store.campaign_id), event, actors=(target,)
                    )
                    updated = value.model_copy(update=dict(vacancy_reviewed_event=event))
                    state, updated = apply_frame(self.game, c, state, updated, event)
                else:
                    if rules.linked(state, value.target_frame):
                        raise WorkflowError(
                            "Actual current known link contradicts a vacant-Frame claim."
                        )
                    updated = value.model_copy(
                        update=dict(
                            phase="complete",
                            vacancy_reviewed_event=event,
                            effect_event=event,
                            completion_event=event,
                            revision=value.revision + 1,
                        )
                    )
                    state = rules.purge_vacant_frame(state, updated, event)
                kind = "m3.virus_frame_occupancy_reviewed"
            self.game.event(
                c,
                viewer.user_id,
                key,
                kind,
                state,
                event_id=event,
                purge=value.id,
                choice=choice,
                account=account,
            )
            if updated.phase == "complete":
                _resolve_work(c, self.game, updated, event)
            else:
                advance(self.game, c, updated, event)
                if updated.role_case:
                    from girlframe.services.m3_role_punishments import synchronize

                    synchronize(self.game, c, None, event)
            return dict(id=identity, phase=updated.phase)

        return VirusService(self.game)._write(
            viewer,
            key,
            "m3.virus_frame_occupancy_review",
            dict(id=identity, revision=revision, choice=choice, account=account),
            operation,
        )

    def inspect(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            action = self.game.action(c, identity)
            _, value = source(c, self.game, action["data"].get("virus_purge", ""))
            if viewer.user_id not in (
                value.creator_controller,
                value.target_controller,
                value.frame_controller,
                value.judge_controller,
            ):
                raise WorkflowError("Only actual original source roles inspect this operation.")
            return dict(
                id=identity,
                state=action["state"],
                revision=action["revision"],
                play="compliance_virus",
                receipt=None,
                modifiers=[],
                result=action["data"]["result"] if action["state"] == "complete" else None,
                phase=value.phase,
                method="PRINTED FIXED11 / NO RNG / NO HEAT"
                if value.role_case and value.kind == "frame"
                else "DICELESS OWNED FACTUAL PROCEDURE",
            )

    def decision(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any], row: dict[str, Any]
    ) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        _, value = source(c, self.game, action["data"]["virus_purge"])
        if (
            row["kind"] != "virus_purge_work"
            or int(row["actor_id"]) != viewer.user_id
            or json.loads(row["body_json"]).get("purge") != value.id
        ):
            raise WorkflowError("Only original source procedure owner can open this decision.")
        return dict(row) | dict(
            virus_purge=True, work_id=value.id, phase=value.phase, case_id=value.role_case
        )
