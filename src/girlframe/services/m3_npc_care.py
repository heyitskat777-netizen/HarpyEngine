"""Local NPC care and consented experimentation on the original Girl’s Assets."""

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
SCIENTIST_VOID = "npc_scientist_void"
JOBS = {
    "doctor": ("girl", "Patch someone up"),
    "mechanic": ("frame", "Fix something"),
    "scientist": ("girl", "Experiment with Void"),
}


class Offer(Model):
    id: str
    scene: str
    npc: ActorRef
    controller: int
    target: ActorRef
    job: Literal["doctor", "mechanic", "scientist"]
    account: str
    event: str
    repaired: str | None = None
    response: str | None = None
    facilitator: int | None = None
    appointment: str | None = None
    void_asset: str | None = None
    void_work: str | None = None
    resisted: bool = False


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
                rule = "npc.npc." + job
                if job == "scientist":
                    access.require_specialist_rule(rule)
                else:
                    access.registry.require_available(rule)
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
            if job in {"doctor", "scientist"}:
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
        if offer.job == "scientist":
            from girlframe.engine.m3_janus_storage import effective_assets

            return {
                x.id: x.name
                for x in effective_assets(state, offer.target)
                if not x.void and x.family == family
            }
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
        alteration: str = "",
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
                    or alteration
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
                gm = appointment = None
                if job == "scientist":
                    gm, appointment = MedicalService(self.store)._handler(c)
                    if cast.facilitator != gm:
                        raise WorkflowError("Use the original facilitated experiment scene")
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
                        facilitator=gm,
                        appointment=appointment,
                    )
                )
                kind = "m3.npc_care_offered"
            else:
                existing = self._pending(c, state, viewer, identity)
                if (
                    target is not None
                    or account
                    or (alteration and (existing.job != "scientist" or asset is None))
                ):
                    raise WorkflowError("Choose one actual original Asset or decline")
                offer = existing.model_copy(update=dict(response=event))
                if asset is not None:
                    cast, current, targets = self._source(
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
                    if existing.job == "scientist":
                        state, offer = self._experiment(c, state, cast, offer, asset, alteration)
                    else:
                        repair(state, existing.target, (asset,), 1)
                        offer = offer.model_copy(update=dict(repaired=asset))
                kind = "m3.npc_care_responded"
            state.facts = [
                x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, offer.id)
            ]
            state.facts.append(dict(kind=KIND, id=offer.id, body=offer.model_dump_json()))
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, offer=offer.id)
            if offer.void_work:
                self._materialize_void(c, offer, event)
            result = dict(id=offer.id, repaired=offer.repaired, pending=offer.response is None)
            if offer.job == "scientist":
                result.update(
                    void_asset=offer.void_asset, void_work=offer.void_work, resisted=offer.resisted
                )
            return result

        return self.store._write(
            viewer,
            key,
            "m3.npc_care_choice",
            dict(card=identity, revision=revision, target=target, account=account, asset=asset)
            | (dict(alteration=alteration) if alteration else {}),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )

    def _experiment(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        offer: Offer,
        asset: str,
        alteration: str,
    ) -> tuple[GameState, Offer]:
        from girlframe.engine.m3_janus_storage import alter, effective_assets
        from girlframe.engine.m3_void import FINAL
        from girlframe.services.p1_facilitator import require_scene_clear

        require_scene_clear(self.game, c, cast.channel)
        if (
            offer.response is None
            or (offer.facilitator, offer.appointment) != MedicalService(self.store)._handler(c)
            or cast.facilitator != offer.facilitator
            or not 1 <= len(alteration.strip()) <= 1200
            or any(x.actor == offer.target and x.stage not in FINAL for x in state.void_thresholds)
        ):
            raise WorkflowError("Describe the actual owned Void gain in its original scene")
        try:
            updated, required = alter(
                state,
                offer.target,
                asset,
                alteration.strip(),
                offer.id,
                offer.response,
                piloting=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        applied = any(x.id == asset and x.void for x in effective_assets(updated, offer.target))
        threshold = any(x.kind == "girl_void_threshold" for x in required)
        return updated, offer.model_copy(
            update=dict(
                void_asset=asset if applied else None,
                void_work=offer.id + ":void:girl" if applied and threshold else None,
                resisted=not applied,
            )
        )

    def _materialize_void(self, c: Connection, offer: Offer, event: str) -> None:
        from girlframe.services.m3_work import related

        assert offer.void_work is not None
        owner = int(offer.target.entity)
        related(
            c,
            self.store,
            dict(campaign_id=self.store.campaign_id, scene_id=offer.scene),
            offer.void_work,
            owner,
            owner,
            "void_threshold",
            dict(
                owner=offer.target.model_dump(mode="json"),
                character=offer.target.incarnation,
                source_action=None,
                source_pdf=19,
                reason=SCIENTIST_VOID,
                case=offer.id,
                details=dict(family="girl"),
            ),
            event,
        )


def void_audience(
    game: GameService, c: Connection, state: GameState, body: dict[str, Any]
) -> list[int]:
    case = next((x for x in _records(state) if x.id == body.get("case")), None)
    if (
        case is None
        or not case.void_work
        or case.facilitator is None
        or (case.facilitator, case.appointment) != MedicalService(game.store)._handler(c)
    ):
        raise WorkflowError("Recover the original NPC experiment’s private audience")
    return sorted({int(case.target.entity), case.facilitator})


def prove_void(
    game: GameService,
    c: Connection,
    state: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    case = next((x for x in _records(state) if x.id == body.get("case")), None)
    if (
        case is None
        or case.job != "scientist"
        or case.target != actor
        or case.scene != row["scene_id"]
        or case.response != row["event_id"]
        or case.void_work != row["id"]
        or not case.void_asset
        or not any(
            asset.id == case.void_asset and asset.void
            for asset in state.sheets[actor.entity].assets
        )
    ):
        raise WorkflowError("Recover the original owned Scientist experiment and Void gain")
    result = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == case.response,
        )
    ).first()
    if not result or tuple(result) != ("m3.npc_care_responded", actor.entity):
        raise WorkflowError("Recover the genuine original NPC experiment receipt")
