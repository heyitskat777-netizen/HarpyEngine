"""Carry out the printed Doctor or Mechanic move on an actual owned damaged Asset."""

from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_doctor import repair
from girlframe.engine.m3_sentinel_shell import holds
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _visible
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "npc_care_offer"
JOBS = {"doctor": ("girl", "Patch someone up"), "mechanic": ("frame", "Fix something")}


class Offer(Model):
    id: str
    scene: str
    npc: ActorRef
    controller: int
    target: ActorRef
    job: Literal["doctor", "mechanic"]
    account: str
    event: str
    repaired: str | None = None
    response: str | None = None


def _records(state: GameState) -> tuple[Offer, ...]:
    return tuple(Offer.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


class NpcCareService:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.game = GameService(store)

    def _gate(self, c: Connection, viewer: GuildViewer, job: str | None = None) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        if job:
            if job not in JOBS or access.registry is None:
                raise WorkflowError("Use a supported printed NPC care job")
            try:
                access.registry.require_available("npc.npc." + job)
            except ValueError as error:
                raise WorkflowError(str(error)) from None

    def _source(
        self,
        c: Connection,
        state: GameState,
        scene: str,
        npc: str,
        job: str,
    ) -> tuple[SceneCast, ActorView, dict[str, ActorView]]:
        cast = next((x for x in state.scene_casts if x.id == scene and x.open), None)
        role = (
            next((x for x in cast.roles if x.actor.kind == "npc" and x.actor.token == npc), None)
            if cast
            else None
        )
        if role is None or cast is None or job not in JOBS:
            raise WorkflowError("Recover the actual original NPC and current scene")
        bound = profiles(c, self.store.campaign_id)
        actor = resolve(state, role.actor, bound, require_current_profile=False)
        if (
            not actor.alive
            or actor.offstage_source
            or actor.cell is None
            or actor.custody
            or actor.controller != role.controller
            or job not in actor.jobs
            or "director" in actor.jobs
        ):
            raise WorkflowError("Recover the actual living NPC in the original role")

        result: dict[str, ActorView] = {}
        for member in cast.roles:
            if member.actor.kind != "pilot":
                continue
            target = resolve(state, member.actor, bound, require_current_profile=False)
            if (
                not target.alive
                or target.rules != "girl_frame"
                or target.offstage_source
                or target.controller != member.controller
                or target.custody not in (None, "free")
                or holds(state, target.ref, "trapped")
                or not _visible(state, actor.ref, target.controller)
            ):
                continue
            if job == "doctor":
                available = target.inside_frame is False and target.cell == actor.cell
            else:
                available = (
                    target.piloting is False
                    and target.frame_cell == actor.cell
                    and target.frame_instance is not None
                    and not state.sheets[target.ref.entity].frame_scrapped
                )
            if available:
                result[target.ref.token] = target
        return cast, actor, result

    @staticmethod
    def _offer_id(scene: str, npc: str, job: str) -> str:
        return f"offer/{scene}/{npc}/{job}"

    @staticmethod
    def _available_assets(state: GameState, offer: Offer) -> dict[str, str]:
        sheet = state.sheets.get(offer.target.entity)
        if sheet is None or sheet.character_id != offer.target.incarnation:
            return {}
        family = JOBS[offer.job][0]
        return {x.id: x.name for x in sheet.assets if x.damaged and x.family == family}

    def tasks(self, c: Connection, viewer: GuildViewer, state: GameState) -> list[dict[str, Any]]:
        try:
            self._gate(c, viewer)
        except WorkflowError:
            return []
        records = _records(state)
        items = [
            dict(id=x.id, revision=state.revision, label=JOBS[x.job][1] + " · your choice")
            for x in records
            if not x.response
            and x.target.entity == str(viewer.user_id)
            and (sheet := state.sheets.get(x.target.entity)) is not None
            and sheet.character_id == x.target.incarnation
        ]
        for scene in state.scene_casts:
            if not scene.open:
                continue
            for role in scene.roles:
                if role.actor.kind != "npc" or role.controller != viewer.user_id:
                    continue
                for job, (_, label) in JOBS.items():
                    try:
                        self._gate(c, viewer, job)
                        _, _, targets = self._source(c, state, scene.id, role.actor.token, job)
                    except (ValueError, WorkflowError):
                        continue
                    if targets:
                        items.append(
                            dict(
                                id=self._offer_id(scene.id, role.actor.token, job),
                                revision=state.revision,
                                label=label,
                            )
                        )
        return items

    def _pending(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> Offer:
        actual = next((x for x in _records(state) if x.id == identity), None)
        if actual is None or actual.response or actual.target.entity != str(viewer.user_id):
            raise WorkflowError("This private NPC care offer is unavailable")
        actor = state.sheets.get(actual.target.entity)
        if actor is None or actor.character_id != actual.target.incarnation:
            raise WorkflowError("Recover the actual original recipient of this offer")
        self._gate(c, viewer, actual.job)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == actual.event,
            )
        )
        proof = _records(GameState.model_validate_json(raw)) if raw else ()
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == actual.event,
            )
        ).first()
        if (
            actual not in proof
            or not event
            or (event.kind, event.actor_id) != ("m3.npc_care_offered", str(actual.controller))
        ):
            raise WorkflowError("Recover the actual NPC offer and original controller")
        return actual

    def _proposal(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[SceneCast, ActorView, dict[str, ActorView], str]:
        parts = identity.split("/")
        if len(parts) != 4 or parts[0] != "offer":
            raise WorkflowError("Use an actual source NPC care card")
        _, scene, npc, job = parts
        self._gate(c, viewer, job)
        cast, actor, targets = self._source(c, state, scene, npc, job)
        if actor.controller != viewer.user_id:
            raise WorkflowError("Only the actual original NPC controller can offer care")
        return cast, actor, targets, job

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if identity.startswith("offer/"):
                _, _, targets, job = self._proposal(c, state, viewer, identity)
                return dict(
                    revision=state.revision,
                    job=job,
                    targets={k: v.label for k, v in targets.items()},
                )
            offer = self._pending(c, state, viewer, identity)
            return dict(
                revision=state.revision,
                job=offer.job,
                account=offer.account,
                assets=self._available_assets(state, offer),
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        target: str | None = None,
        account: str = "",
        asset: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            if revision != state.revision:
                raise WorkflowError("STALE_NPC_CARE: reopen the actual private choice")
            event = str(uuid4())
            if identity.startswith("offer/"):
                cast, actor, targets, job = self._proposal(c, state, viewer, identity)
                if (
                    target not in targets
                    or not 0 < len(account.strip()) <= 1200
                    or asset is not None
                ):
                    raise WorkflowError(
                        "Choose the actual available recipient and describe your NPC's offer"
                    )
                recipient = targets[target].ref
                if any(
                    not x.response and x.npc == actor.ref and x.target == recipient and x.job == job
                    for x in _records(state)
                ):
                    raise WorkflowError(
                        "This actual NPC already offered this care to the original Girl"
                    )
                offer = Offer.model_validate(
                    dict(
                        id=str(uuid4()),
                        scene=cast.id,
                        npc=actor.ref,
                        controller=actor.controller,
                        target=recipient,
                        job=job,
                        account=account.strip(),
                        event=event,
                    )
                )
                kind = "m3.npc_care_offered"
            else:
                existing = self._pending(c, state, viewer, identity)
                if target is not None or account:
                    raise WorkflowError("Choose one actual damaged Asset or decline")
                if asset is not None:
                    _, current, targets = self._source(
                        c,
                        state,
                        existing.scene,
                        existing.npc.token,
                        existing.job,
                    )
                    if (
                        current.controller != existing.controller
                        or existing.target.token not in targets
                        or asset not in self._available_assets(state, existing)
                        or self.game.immediate_work(c, viewer.user_id)
                    ):
                        raise WorkflowError(
                            "Recover the actual source, patient and eligible damaged Asset"
                        )
                    repair(state, existing.target, (asset,), 1)
                offer = existing.model_copy(update=dict(repaired=asset, response=event))
                kind = "m3.npc_care_responded"
            state.facts = [
                x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, offer.id)
            ]
            state.facts.append(dict(kind=KIND, id=offer.id, body=offer.model_dump_json()))
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, offer=offer.id)
            return dict(id=offer.id, repaired=offer.repaired, pending=offer.response is None)

        return self.store._write(
            viewer,
            key,
            "m3.npc_care_choice",
            dict(card=identity, revision=revision, target=target, account=account, asset=asset),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )
