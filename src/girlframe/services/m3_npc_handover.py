"""Local NPC job offers move an actual possession only with the original Girl's choice."""

from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_items
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_item_state import HeldItem
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

Job = Literal["fan", "patron", "smuggler"]
LABELS: dict[Job, str] = {
    "fan": "Steal something personal",
    "patron": "Offer exactly what someone wants",
    "smuggler": "Get them something they aren’t supposed to have",
}
KIND = "npc_job_handover"


class Handover(Model):
    id: str
    scene: str
    channel: int
    npc: ActorRef
    controller: int
    girl: ActorRef
    job: Job
    account: str
    item: str | None = None
    item_event: str | None = None
    decision: str | None = None
    transferred: str | None = None


def records(state: GameState) -> tuple[Handover, ...]:
    return tuple(
        Handover.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


class NpcHandoverService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer, job: Job | None = None) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        if job is not None:
            if job not in LABELS:
                raise WorkflowError("Choose a supported original NPC job")
            try:
                access.require_specialist_rule("npc.npc." + job)
            except ValueError as error:
                raise WorkflowError(str(error)) from None

    def _local(
        self, c: Connection, state: GameState, channel: int, ref: ActorRef, job: Job
    ) -> tuple[SceneCast, ActorView, dict[str, ActorView]]:
        from girlframe.engine.m3_sentinel_shell import holds

        cast = _cast(self.game, c, state, channel)
        bound = profiles(c, self.store.campaign_id)
        npc = resolve(state, ref, bound, require_current_profile=False)
        if (
            ref.kind != "npc"
            or not npc.alive
            or job not in npc.jobs
            or "director" in npc.jobs
            or npc.offstage_source
            or npc.custody
            or npc.cell is None
            or not any(x.actor == ref and x.controller == npc.controller for x in cast.roles)
            or job == "smuggler"
            and MedicalService(self.store)._handler(c)[0] != npc.controller
        ):
            raise WorkflowError("Use the original local NPC in their authorized job")
        targets = {}
        for role in cast.roles:
            if role.actor.kind != "pilot" or role.controller == npc.controller:
                continue
            girl = resolve(state, role.actor, bound, require_current_profile=False)
            if (
                girl.alive
                and girl.rules == "girl_frame"
                and girl.controller == role.controller
                and girl.cell == npc.cell
                and girl.inside_frame is False
                and not girl.offstage_source
                and girl.custody in (None, "free")
                and not holds(state, girl.ref, "trapped")
            ):
                targets[girl.ref.token] = girl
        return cast, npc, targets

    def _items(self, c: Connection, state: GameState, holder: ActorRef) -> dict[str, HeldItem]:
        return {
            item.id: prove_item(c, self.game, state, item.id)
            for item in state.held_items
            if item.holder == holder
            and item.asset_json is None
            and item.origin_asset_json is None
            and not item.weapon
            and item.condition == "intact"
            and item.location_mode == "carried"
        }

    def menu(self, viewer: GuildViewer, channel: int, ref: ActorRef, job: Job) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer, job)
            state = load_state(c, self.store.campaign_id)
            _, npc, targets = self._local(c, state, channel, ref, job)
            if npc.controller != viewer.user_id:
                raise WorkflowError("Use your original NPC’s owned job")
            items = self._items(c, state, ref) if job != "fan" else {}
            return dict(
                revision=state.revision,
                targets={key: x.label for key, x in targets.items()},
                items={key: x.name for key, x in items.items()},
            )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        ref: ActorRef,
        job: Job,
        revision: int,
        target: str,
        account: str,
        selection: str | None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            cast, npc, targets = self._local(c, state, channel, ref, job)
            if (
                npc.controller != viewer.user_id
                or revision != state.revision
                or target not in targets
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Refresh the original local job and its recipient")
            item = (
                self._items(c, state, npc.ref).get(selection)
                if selection is not None and job != "fan"
                else None
            )
            if (job == "fan" and selection is not None) or (job != "fan" and item is None):
                raise WorkflowError("Choose an actual item already held by this NPC")
            girl = targets[target]
            if any(
                not x.decision and x.npc == npc.ref and x.girl == girl.ref and x.job == job
                for x in records(state)
            ):
                raise WorkflowError("Recover the original pending NPC offer")
            event = str(uuid4())
            offer = Handover(
                id=event,
                scene=cast.id,
                channel=channel,
                npc=npc.ref,
                controller=npc.controller,
                girl=girl.ref,
                job=job,
                account=account.strip(),
                item=item.id if item else None,
                item_event=(item.state_event or item.source_event) if item else None,
            )
            state.facts.append(dict(kind=KIND, id=offer.id, body=offer.model_dump_json()))
            self.game.event(
                c, viewer.user_id, key, "m3.npc_handover_proposed", state, event_id=event
            )
            return dict(id=event)

        return self.store._write(
            viewer,
            key,
            "m3.npc_handover_propose",
            dict(
                channel=channel,
                actor=ref.model_dump(mode="json"),
                job=job,
                revision=revision,
                target=target,
                account=account,
                item=selection,
            ),
            operation,
            authorize=lambda c: self._gate(c, viewer, job),
            auto_audit=False,
        )

    def tasks(self, c: Connection, state: GameState, viewer: GuildViewer) -> tuple[Handover, ...]:
        pending = []
        for offer in records(state):
            girl = state.sheets.get(offer.girl.entity)
            if (
                offer.decision
                or offer.girl.entity != str(viewer.user_id)
                or girl is None
                or girl.character_id != offer.girl.incarnation
            ):
                continue
            try:
                self._gate(c, viewer, offer.job)
            except WorkflowError:
                continue
            pending.append(offer)
        return tuple(pending)

    def _pending(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> Handover:
        offer = next((x for x in self.tasks(c, state, viewer) if x.id == identity), None)
        if offer is None:
            raise WorkflowError("This private NPC offer is unavailable")
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == offer.id,
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind == "m3.npc_handover_proposed",
                t.events.c.actor_id == str(offer.controller),
            )
        )
        if raw is None or offer not in records(GameState.model_validate_json(raw)):
            raise WorkflowError("Recover the original offer and its actual source")
        return offer

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            offer = self._pending(c, state, viewer, identity)
            items = self._items(c, state, offer.girl if offer.job == "fan" else offer.npc)
            if offer.job != "fan":
                exact = items.get(offer.item or "")
                items = (
                    {exact.id: exact}
                    if exact and (exact.state_event or exact.source_event) == offer.item_event
                    else {}
                )
            return dict(
                revision=state.revision,
                job=offer.job,
                account=offer.account,
                items={key: x.name for key, x in items.items()},
            )

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, choice: str | None
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            offer = self._pending(c, state, viewer, identity)
            if revision != state.revision:
                raise WorkflowError("Refresh the current private handover")
            event = str(uuid4())
            transferred = None
            if choice is not None:
                state = self._transfer(c, state, offer, choice, event)
                transferred = state.item_transfers[-1].id
            changed = offer.model_copy(update=dict(decision=event, transferred=transferred))
            state.facts = [
                x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, identity)
            ]
            state.facts.append(dict(kind=KIND, id=identity, body=changed.model_dump_json()))
            self.game.event(
                c, viewer.user_id, key, "m3.npc_handover_decided", state, event_id=event
            )
            return dict(id=identity, transfer=transferred)

        return self.store._write(
            viewer,
            key,
            "m3.npc_handover_respond",
            dict(id=identity, revision=revision, choice=choice),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )

    def _transfer(
        self, c: Connection, state: GameState, offer: Handover, choice: str, event: str
    ) -> GameState:
        require_scene_clear(self.game, c, offer.channel)
        MedicalService(self.store)._idle(c)
        cast, npc, targets = self._local(c, state, offer.channel, offer.npc, offer.job)
        donor, receiver = (offer.girl, offer.npc) if offer.job == "fan" else (offer.npc, offer.girl)
        item = self._items(c, state, donor).get(choice)
        if (
            cast.id != offer.scene
            or npc.controller != offer.controller
            or offer.girl.token not in targets
            or item is None
            or offer.job != "fan"
            and (
                item.id != offer.item or (item.state_event or item.source_event) != offer.item_event
            )
        ):
            raise WorkflowError("Recover the original participants and actual possession")
        history = t.m2["m2_state_history"]
        before = c.scalar(
            sa.select(history.c.event_id)
            .where(history.c.campaign_id == self.store.campaign_id)
            .order_by(history.c.revision.desc())
            .limit(1)
        )
        if before is None:
            raise WorkflowError("Recover the original item custody")
        try:
            updated = m3_items.take(
                state,
                donor,
                receiver,
                profiles(c, self.store.campaign_id),
                item.id,
                offer.id,
                event,
                offer.account,
                origin_event=before,
                scene=offer.scene,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        updated.item_transfers[-1] = updated.item_transfers[-1].model_copy(
            update=dict(source_kind=KIND)
        )
        return updated
