"""Actual Timeskip-funded Requisitions and a finite original Handler advancement."""

import json
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection
from sqlalchemy.engine import RowMapping

from girlframe.database import tables as t
from girlframe.engine import m3_comforts as comforts
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine import m3_scene_requisitions as scenes
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import PermissionFlow
from girlframe.engine.m3_intracadre_marriage import records as permission_records
from girlframe.engine.m3_requisition_state import ComfortReceipt, SceneReceipt
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_plays import _ordinary_scene_idle
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.m3_timeskip import RULE, Timeskip, TimeskipService, records
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

REQUISITIONS = {
    "creature_comforts": "Creature Comforts",
    "privacy": "Privacy",
    "visiting_home": "Visiting Home",
}


def _original_event(game: GameService, c: Connection, event: str) -> RowMapping:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the actual Timeskip source event")
    return row


def prove_timeskip_requisition(
    game: GameService, c: Connection, state: GameState, receipt: ComfortReceipt | SceneReceipt
) -> None:
    source = _original_event(game, c, receipt.source_event)
    identity = json.loads(source["payload_json"]).get("timeskip_id")
    case = next((x for x in records(state) if x.id == identity), None)
    before, born = snapshots(game, c, receipt.source_event)
    start = next((x for x in records(born) if x.id == identity), None)
    owner = receipt.actor
    prior = before.sheets.get(owner.entity)
    current = born.sheets.get(owner.entity)
    if (
        case is None
        or start is None
        or source["kind"] != "m3.timeskip_requisition_granted"
        or source["actor_id"] != owner.entity
        or receipt.id != receipt.source_event
        or receipt not in born.requisitions
        or receipt.source_offer != "timeskip:" + case.id
        or receipt.price != 0
        or owner not in case.rewrite_targets
        or owner not in start.rewrite_targets
        or case.requisitions.get(owner.token) != receipt.id
        or start.requisitions.get(owner.token) != receipt.id
        or prior is None
        or current is None
        or prior.character_id != owner.incarnation
        or current.character_id != owner.incarnation
        or prior.permissions != current.permissions
        or any(x.event == receipt.source_event for x in permission_records(born, PermissionFlow))
    ):
        raise WorkflowError(
            "Recover the actual original Timeskip Requisition and zero-cost receipt"
        )


def prove_timeskip_award(
    game: GameService, c: Connection, state: GameState, award: advancement.Award
) -> None:
    source = _original_event(game, c, award.award_event)
    born = _history(c, game, award.award_event)
    initial = next((x for x in advancement.awards(born) if x.id == award.id), None)
    case = next((x for x in records(state) if x.id == award.source_work), None)
    original = next((x for x in records(born) if x.id == award.source_work), None)
    if (
        case is None
        or original is None
        or initial is None
        or source["kind"] != "m3.timeskip_handler_award_granted"
        or json.loads(source["payload_json"]).get("timeskip_id") != case.id
        or source["actor_id"] != award.handler.entity
        or initial.phase != "held"
        or initial.rule != RULE
        or active_handler(born) != award.handler
        or original.handler_award != award.id
        or case.handler_award != award.id
        or initial.handler != award.handler
        or initial.appointment != award.appointment
        or original.appointment != award.appointment
        or initial.award_event != award.award_event
        or initial.account != award.account
    ):
        raise WorkflowError("Recover the original finite Timeskip Handler advancement")


class TimeskipRewards:
    def __init__(self, timeskip: TimeskipService):
        self.timeskip, self.game, self.store = timeskip, timeskip.game, timeskip.store

    def _world(self, c: Connection, viewer: GuildViewer, case: Timeskip) -> None:
        Access(self.store).authorize(c, viewer, "economy", director_response=True)
        if case.step != "benefits":
            raise WorkflowError("Reopen the same original Timeskip benefits")
        self.game.unpaused(c)
        _ordinary_scene_idle(c, self.game)

    def _companions(self, state: GameState, owner: int) -> dict[ActorRef, str]:
        return {
            current_ref(state, uid): state.sheets[str(uid)].callsign
            for uid in state.order
            if uid != owner
        }

    def menu(
        self,
        c: Connection,
        state: GameState,
        case: Timeskip,
        viewer: GuildViewer,
        *,
        choose_requisition: bool,
    ) -> dict[str, Any]:
        Access(self.store).authorize(c, viewer, "economy", director_response=True)
        if choose_requisition:
            return dict(
                companions={
                    x.token: name for x, name in self._companions(state, viewer.user_id).items()
                },
                requisitions=REQUISITIONS,
            )
        award = next((x for x in advancement.awards(state) if x.id == case.handler_award), None)
        return dict(
            award=award.phase if award else "claim",
            can_continue=bool(
                award
                and award.phase == "spent"
                and len(case.requisitions) == len(case.rewrite_targets)
            ),
        )

    def requisition(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: str,
        companion: str | None,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            case = self.timeskip._case(c, state, viewer, identity)
            self._world(c, viewer, case)
            actor = next((x for x in case.rewrite_targets if x.entity == str(viewer.user_id)), None)
            if (
                state.revision != revision
                or actor is None
                or actor.token in case.requisitions
                or choice not in REQUISITIONS
                or not 0 < len(account.strip()) <= 1200
                or (choice == "privacy") != bool(companion)
            ):
                raise WorkflowError("Choose one original Requisition for your current Girl")
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            peer = next(
                (x for x in self._companions(state, viewer.user_id) if x.token == companion), None
            )
            if companion and peer is None:
                raise WorkflowError("Choose one actual current other Girl for Privacy")
            bound = profiles(c, self.store.campaign_id)
            actual = resolve(state, actor, bound)
            if actual.controller != viewer.user_id or actual.offstage_source:
                raise WorkflowError("Recover the actual available original Timeskip recipient")
            event, offer = str(uuid4()), "timeskip:" + case.id
            if choice == "creature_comforts":
                state = comforts.grant_offered(
                    state,
                    actor,
                    bound,
                    actual.source_sha256,
                    event,
                    event,
                    account.strip(),
                    offer,
                )
            else:
                state = scenes.grant_offered(
                    state,
                    actor,
                    bound,
                    actual.source_sha256,
                    cast(Literal["privacy", "visiting_home"], choice),
                    peer,
                    account.strip(),
                    event,
                    event,
                    offer,
                )
            case = case.model_copy(
                update=dict(requisitions=case.requisitions | {actor.token: event})
            )
            return self.timeskip._save(c, state, viewer, key, case, "requisition_granted", event)

        return self.timeskip._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                requisition=choice,
                companion=companion,
                account=account,
            ),
            operation,
        )

    def award(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, *, finish: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            case = self.timeskip._case(c, state, viewer, identity)
            self._world(c, viewer, case)
            handler = active_handler(state)
            if (
                viewer.user_id != case.gm
                or state.revision != revision
                or handler is None
                or handler.entity != str(viewer.user_id)
            ):
                raise WorkflowError("Only the actual original Handler owns this advancement")
            event = str(uuid4())
            if finish:
                if case.handler_award is None or len(case.requisitions) != len(
                    case.rewrite_targets
                ):
                    raise WorkflowError("Finish the original Girls’ and Handler’s benefits first")
                _, _, _, _, award = HandlerAdvancementService(self.store)._proof(
                    c, case.handler_award
                )
                if award is None or award.phase != "spent":
                    raise WorkflowError(
                        "Complete the original Handler advancement before moving on"
                    )
                for target in case.rewrite_targets:
                    receipt = next(
                        (
                            x
                            for x in state.requisitions
                            if x.id == case.requisitions.get(target.token)
                        ),
                        None,
                    )
                    if not isinstance(receipt, (ComfortReceipt, SceneReceipt)):
                        raise WorkflowError("Each original Girl needs an actual Timeskip receipt")
                    prove_timeskip_requisition(self.game, c, state, receipt)
                case = case.model_copy(update=dict(step="electives"))
                return self.timeskip._save(c, state, viewer, key, case, "benefits_completed", event)
            if case.handler_award is not None:
                raise WorkflowError("Continue the actual Timeskip award in the private Inbox")
            value = advancement.Award(
                id="timeskip:" + case.id,
                rule=RULE,
                handler=handler,
                appointment=case.appointment,
                source_work=case.id,
                source_event=event,
                award_event=event,
                account="The original Handler’s advancement from the agreed Timeskip.",
            )
            advancement.grant(state, value)
            case = case.model_copy(update=dict(handler_award=value.id))
            return self.timeskip._save(c, state, viewer, key, case, "handler_award_granted", event)

        return self.timeskip._write(
            viewer, key, dict(id=identity, revision=revision, finish_benefits=finish), operation
        )
