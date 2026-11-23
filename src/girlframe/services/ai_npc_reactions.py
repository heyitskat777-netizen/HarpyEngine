"""Activity NPC dialogue, reviewed guide offers and private canon leads."""

import json
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from pydantic import Field, ValidationError
from sqlalchemy import Connection, RowMapping, Select

from girlframe.ai.briefing import BriefingPolicy
from girlframe.ai.conversation import RULES_IN_PROSE
from girlframe.ai.npc_reaction import (
    GUIDE_PROMPT_VERSION,
    LEAD_PROMPT_VERSION,
    PROMPT_VERSION,
    NpcReactionContext,
    NpcReactionGateway,
    NpcReactionResult,
    NpcReactionText,
)
from girlframe.ai.observation import Observation, SceneTurn
from girlframe.ai.openai_npc_reaction import OpenAINpcReactionGateway
from girlframe.ai.provider import ProviderError
from girlframe.database import tables as t
from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import GameState, Model
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_defeat import offstage_travel
from girlframe.engine.m3_world_state import Npc
from girlframe.scenes.campaign_time import SLOTS, Identity, Position, ScenePlan
from girlframe.scenes.canon import CanonWindow, KnowledgeGrant, Statement
from girlframe.services import campaign_time_history as calendar
from girlframe.services import canon_history
from girlframe.services.activity_dialogue import (
    NPC_ADDRESSED,
    current_turn,
    has_delivered_reply,
    npc_owned,
)
from girlframe.services.ai_attempts import REACTION_RESERVATION, reserve_attempt
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.canon import CanonService, fact_identity
from girlframe.services.director_observation import DirectorObservationService, _digest
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ADDRESSED = NPC_ADDRESSED
REQUESTED = "ai.npc_reaction_requested"
RESULT = "ai.npc_reaction_result"
REVIEW = "ai.npc_reaction_reviewed"
PUBLISHED = "activity.npc_reaction_published"
GUIDE_RESPONSE = "activity.npc_guide_response"
GUIDE_HANDOFF = "activity.npc_guide_handoff"
NPC_WITNESS = "canon.npc_witnessed"
GuideChoice = Literal["follow", "decline"]


class Address(Model):
    window: CanonWindow
    npc_id: str = Field(min_length=1, max_length=100)
    npc_name: str = Field(min_length=1, max_length=120)
    speaker: str
    controller: Snowflake
    submission_id: Identity
    statement: Statement
    source_turn: SceneTurn | None = Field(default=None, exclude_if=lambda value: value is None)


class GuideDestination(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)


class NpcLead(Model):
    fact_id: Identity
    witness_id: Identity
    statement: Statement


class ReactionRequest(Model):
    address_id: Identity
    window: CanonWindow
    game_revision: int
    model: str
    prompt_version: str
    guide: GuideDestination | None = Field(default=None, exclude_if=lambda value: value is None)
    lead: NpcLead | None = Field(default=None, exclude_if=lambda value: value is None)

    @property
    def expected_prompt(self) -> str:
        if self.guide is not None:
            return GUIDE_PROMPT_VERSION
        if self.lead is not None:
            return LEAD_PROMPT_VERSION
        return PROMPT_VERSION


@dataclass(frozen=True)
class LiveScene:
    window: CanonWindow
    state: GameState
    participants: set[int]
    npcs: dict[str, Npc]


class NpcReactionService:
    def __init__(self, store: OnboardingStore, gateway: NpcReactionGateway | None = None):
        self.store = store
        self.campaign = store.campaign_id
        self.canon = CanonService(store)
        self.missions = MissionService(store)
        self.timeline = CampaignTimeService(store)
        self.gateway = gateway if gateway is not None else OpenAINpcReactionGateway()

    def _policy(self) -> BriefingPolicy:
        policy = self.store.policy.ai_npc_reactions
        if policy is None:
            raise WorkflowError("AI NPC reactions are disabled in campaign policy.")
        return policy

    def _live(self, c: Connection, viewer: GuildViewer, scene_id: str) -> LiveScene:
        channel = self.canon._channel(c, scene_id)
        window = self.canon.current_window(c, viewer, channel, facilitator=True)
        scene = self.canon.game.scene(c, channel, check_slot=False)
        lock = self.canon.game.lock(c, channel)
        if lock is not None and lock["state"] != "released":
            raise WorkflowError("Resolve the current Play before drafting an NPC reaction.")
        state = load_state(c, self.campaign)
        participants = self.canon._participants(c, scene)
        cast_roles = next(
            (item.roles for item in state.scene_casts if item.id == scene_id and item.open), ()
        )
        actual_handler = self.canon.handler.current(c)[1].handler_id
        eligible = {
            role.actor.entity
            for role in cast_roles
            if role.actor.kind == "npc" and role.controller == state.handler == actual_handler
        }
        world_npcs = state.world.npcs if state.world is not None else ()
        npcs = {
            npc.id: npc
            for npc in world_npcs
            if npc.id in eligible
            and npc.controller == actual_handler
            and npc.revealed
            and npc.alive
            and npc.captive_of is None
            and not {"director", "prisoner"}.intersection(npc.jobs)
            and offstage_travel(state, ActorRef(kind="npc", entity=npc.id)) is None
        }
        return LiveScene(window, state, participants, npcs)

    def _pilot(self, c: Connection, scene: LiveScene, user_id: int) -> str:
        pilot = scene.state.sheets.get(str(user_id))
        if user_id not in scene.participants or pilot is None or pilot.medical_state != "fit":
            raise WorkflowError(
                "Only an actual cast Pilot can submit an NPC address in this scene."
            )
        principal = self.canon.principal(c, user_id)
        if (
            principal is None
            or not principal.startswith("pilot:")
            or not self.canon.handler._member(c, user_id)
        ):
            raise WorkflowError("The original Pilot is no longer available in this scene.")
        return principal

    def targets(self, viewer: GuildViewer, scene_id: str) -> dict[str, Any]:
        scene_id = fact_identity(scene_id)
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.canon._access(c, viewer)
            self._policy()
            scene = self._live(c, viewer, scene_id)
            self._pilot(c, scene, viewer.user_id)
            return {
                "window": scene.window.model_dump(mode="json"),
                "npcs": [{"id": npc.id, "name": npc.name} for npc in scene.npcs.values()],
            }

    def _audit(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        kind: str,
        data: dict[str, Any],
        *,
        event_id: str | None = None,
        event_index: int = 0,
    ) -> str:
        return self.store._audit(
            c,
            viewer.user_id,
            key,
            kind,
            data,
            event_id=event_id,
            event_index=event_index,
            ruleset_version=PROMPT_VERSION,
        )

    def _observed_turn(self, c: Connection, scene: str, link: SceneTurn) -> Observation | None:
        observer = DirectorObservationService(self.store)
        row = observer._scene(c, scene)
        state = observer._state(c, scene)
        if state.activity_epoch is None or (
            state.policy.mode != "shadow" or not observer._consented(c, row, state)
        ):
            return None
        source = current_turn(c, self.campaign, scene, link)
        return source if source and source.sequence > state.capture_floor else None

    def address(
        self,
        viewer: GuildViewer,
        submission_id: str,
        expected: CanonWindow,
        npc_id: str,
        statement: str,
        *,
        source_turn: SceneTurn | None = None,
    ) -> str:
        submission_id = fact_identity(submission_id)
        if expected.scene_revision is None:
            raise WorkflowError(
                "Refresh the current Activity scene before submitting this address."
            )
        key = f"activity.npc-address:{viewer.user_id}:{submission_id}"

        def operation(c: Connection, channel: int) -> str:
            self._policy()
            scene = self._live(c, viewer, expected.scene_id)
            speaker = self._pilot(c, scene, viewer.user_id)
            npc = scene.npcs.get(npc_id)
            if npc is None:
                raise WorkflowError("Choose an eligible NPC actually cast in this scene.")
            if source_turn is not None:
                observed = self._observed_turn(c, expected.scene_id, source_turn)
                if (
                    observed is None
                    or observed.author_id != str(viewer.user_id)
                    or observed.actor.kind != "pilot"
                    or speaker != f"pilot:{observed.actor.incarnation}"
                    or observed.text != statement
                    or observed.fictional_channel != "comms"
                    or observed.gm_addressed
                    or observed.covers_turn is not None
                ):
                    raise WorkflowError("NPC_TURN_UNAVAILABLE: choose your current spoken turn.")
                if npc_owned(c, self.campaign, expected.scene_id, (source_turn.source_id,)):
                    raise WorkflowError("NPC_HAS_FLOOR: this turn already has an NPC address.")
                if has_delivered_reply(c, self.campaign, expected.scene_id, source_turn.source_id):
                    raise WorkflowError("NPC_TURN_ANSWERED: use a new turn to address the NPC.")
            try:
                addressed = Address(
                    window=expected,
                    npc_id=npc.id,
                    npc_name=npc.name,
                    speaker=speaker,
                    controller=npc.controller,
                    submission_id=submission_id,
                    statement=statement,
                    source_turn=source_turn,
                )
            except ValidationError:
                raise WorkflowError("Enter a spoken address of 1–600 characters.") from None
            return self._audit(c, viewer, key, ADDRESSED, addressed.model_dump(mode="json"))

        return self.canon._in_window(
            viewer,
            key,
            ADDRESSED,
            expected,
            {
                "npc_id": npc_id,
                "statement": statement,
                **({"source_turn": source_turn.model_dump(mode="json")} if source_turn else {}),
            },
            operation,
            facilitator=False,
        )

    def addresses(self, viewer: GuildViewer, scene_id: str) -> list[dict[str, Any]]:
        scene_id = fact_identity(scene_id)
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            facilitator = viewer.user_id == self.store.policy.canon_facilitator_id
            self.canon._access(c, viewer, facilitator=facilitator)
            query = calendar.query(self.campaign, ADDRESSED).where(
                sa.func.json_extract(t.events.c.payload_json, "$.window.scene_id") == scene_id
            )
            controller = viewer.user_id == self.canon.handler.current(c)[1].handler_id
            if not facilitator and controller:
                query = query.where(
                    sa.func.json_extract(t.events.c.payload_json, "$.controller") == viewer.user_id
                )
            elif not facilitator:
                query = query.where(
                    t.events.c.actor_id == str(viewer.user_id),
                    sa.func.json_extract(t.events.c.payload_json, "$.speaker")
                    == self.canon.principal(c, viewer.user_id),
                )
            return [
                {
                    "id": row["id"],
                    "npc_id": address.npc_id,
                    "npc_name": address.npc_name,
                    "statement": address.statement,
                    "position": address.window.position.model_dump(mode="json"),
                }
                for row in c.execute(query.order_by(t.events.c.seq.desc()).limit(25)).mappings()
                for address in (Address.model_validate_json(row["payload_json"]),)
            ]

    def _row(self, c: Connection, kind: str, identity: str) -> RowMapping:
        row = (
            c.execute(calendar.query(self.campaign, kind).where(t.events.c.id == identity))
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This NPC reaction record is unavailable.")
        return row

    def _source(
        self,
        c: Connection,
        viewer: GuildViewer,
        address_id: str,
        owner: int,
    ) -> tuple[LiveScene, Address, Npc]:
        row = self._row(c, ADDRESSED, address_id)
        address = Address.model_validate_json(row["payload_json"])
        scene = self._live(c, viewer, address.window.scene_id)
        npc = scene.npcs.get(address.npc_id)
        if (
            npc is None
            or npc.controller != owner
            or address.controller != owner
            or scene.window.anchor_id != address.window.anchor_id
            or self._pilot(c, scene, int(row["actor_id"])) != address.speaker
        ):
            raise WorkflowError(
                "STALE_REACTION: the original NPC or Pilot is unavailable in this scene."
            )
        if (
            address.source_turn
            and self._observed_turn(c, address.window.scene_id, address.source_turn) is None
        ):
            raise WorkflowError(
                "STALE_REACTION: the addressed turn was revised or its consent changed."
            )
        return scene, address, npc

    def _published_from(self, address_id: str) -> Select[Any]:
        return calendar.query(self.campaign, PUBLISHED).where(
            sa.func.json_extract(t.events.c.payload_json, "$.address_id") == address_id
        )

    @staticmethod
    def _destinations(state: GameState) -> dict[str, GuideDestination]:
        # All saved locations are on the campaign map. Operational status is rules-owned.
        locations = state.world.locations if state.world is not None else ()
        return {
            item.id: GuideDestination(id=item.id, name=item.name)
            for item in locations
            if item.operational
        }

    def destinations(self, viewer: GuildViewer, scene_id: str) -> list[dict[str, Any]]:
        scene_id = fact_identity(scene_id)
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.canon._access(c, viewer)
            self.canon.handler.authorize(c, viewer)
            scene = self._live(c, viewer, scene_id)
            return [
                item.model_dump(mode="json") for item in self._destinations(scene.state).values()
            ]

    def _witness(self, c: Connection, npc_id: str, fact_id: str) -> str | None:
        return c.scalar(
            calendar.query(self.campaign, NPC_WITNESS)
            .where(
                sa.func.json_extract(t.events.c.payload_json, "$.npc_id") == npc_id,
                sa.func.json_extract(t.events.c.payload_json, "$.fact_id") == fact_id,
            )
            .with_only_columns(t.events.c.id)
            .limit(1)
        )

    def _lead(self, c: Connection, scene: LiveScene, npc: Npc, fact_id: str) -> NpcLead:
        self.canon._validate_refs(c, (fact_id,))
        witness = self._witness(c, npc.id, fact_id)
        fact = self.canon._fact(c, fact_id)
        if witness is None or fact.window.position.order > scene.window.position.order:
            raise WorkflowError("Choose a current fact this NPC witnessed.")
        return NpcLead(fact_id=fact_id, witness_id=witness, statement=fact.statement)

    def lead_controls(
        self, viewer: GuildViewer, scene_id: str, *, facilitator: bool
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.canon._access(c, viewer, facilitator=facilitator)
            if not facilitator:
                self.canon.handler.authorize(c, viewer)
            scene = self._live(c, viewer, scene_id)
            states = canon_history.statuses(c, self.campaign)
            if facilitator:
                return {
                    "window": scene.window.model_dump(mode="json"),
                    "npcs": [{"id": npc.id, "name": npc.name} for npc in scene.npcs.values()],
                    "facts": [
                        {"fact_id": identity, "statement": fact.statement}
                        for identity in c.scalars(
                            calendar.query(self.campaign, canon_history.FACT)
                            .where(
                                sa.func.json_extract(t.events.c.payload_json, "$.window.scene_id")
                                == scene_id
                            )
                            .with_only_columns(t.events.c.id)
                        )
                        if states[identity] == "current"
                        and (fact := self.canon._fact(c, identity)).window.position.order
                        <= scene.window.position.order
                    ],
                }
            recorded: dict[str, list[dict[str, str]]] = {}
            for _, data in calendar.history(c, self.campaign, NPC_WITNESS):
                npc_id, fact_id = data["npc_id"], data["fact_id"]
                if npc_id in scene.npcs and states.get(fact_id) == "current":
                    fact = self.canon._fact(c, fact_id)
                    if fact.window.position.order <= scene.window.position.order:
                        recorded.setdefault(npc_id, []).append(
                            {"fact_id": fact_id, "statement": fact.statement}
                        )
            return recorded

    def witness_lead(
        self,
        viewer: GuildViewer,
        submission_id: str,
        window: CanonWindow,
        npc_id: str,
        fact_id: str,
    ) -> str:
        submission_id, fact_id = map(fact_identity, (submission_id, fact_id))
        key = f"activity.npc-witness:{viewer.user_id}:{submission_id}"

        def operation(c: Connection, channel: int) -> str:
            scene = self._live(c, viewer, window.scene_id)
            if npc_id not in scene.npcs:
                raise WorkflowError("Choose an eligible NPC cast in this scene.")
            self.canon._validate_refs(c, (fact_id,))
            fact = self.canon._fact(c, fact_id)
            if (
                fact.window.scene_id != window.scene_id
                or fact.window.position.order > window.position.order
            ):
                raise WorkflowError("Choose a current fact established in this scene.")
            existing = self._witness(c, npc_id, fact_id)
            if existing is not None:
                return existing
            return self.canon._audit(
                c,
                viewer,
                key,
                NPC_WITNESS,
                {"npc_id": npc_id, "fact_id": fact_id, "window": window.model_dump(mode="json")},
            )

        if window.scene_revision is None:
            raise WorkflowError("Refresh this Activity scene before recording an NPC witness.")
        return self.canon._in_window(
            viewer,
            key,
            NPC_WITNESS,
            window,
            {"npc_id": npc_id, "fact_id": fact_id},
            operation,
            facilitator=True,
        )

    def reportable_leads(self, viewer: GuildViewer, scene_id: str) -> dict[str, Any] | None:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.canon._access(c, viewer)
            channel = self.canon._channel(c, scene_id)
            window = self.canon.current_window(c, viewer, channel, facilitator=False)
            principal = self.canon.principal(c, viewer.user_id)
            handler = self.canon.handler.current(c)[1].handler_id
            scene = self.canon.game.scene(c, channel, check_slot=False)
            if (
                principal is None
                or not principal.startswith("pilot:")
                or handler is None
                or handler not in self.canon._participants(c, scene)
                or not self.canon.handler._member(c, handler)
            ):
                return None
            receiver = self.canon.principal(c, handler)
            if receiver is None:
                return None
            reported = {
                grant.source_grant_id
                for _, grant in self.canon._grants_for(c, handler, receiver)
                if grant.method == "reported"
            }
            states = canon_history.statuses(c, self.campaign)
            facts = [
                {
                    "fact_id": grant.fact_id,
                    "statement": self.canon._fact(c, grant.fact_id).statement,
                }
                for row, grant in self.canon._grants_for(c, viewer.user_id, principal)
                if grant.method == "told"
                and row["id"] not in reported
                and states.get(grant.fact_id) == "current"
                and grant.learned_at.order <= window.position.order
            ]
            return {"window": window.model_dump(mode="json"), "facts": facts} if facts else None

    def queue(
        self,
        viewer: GuildViewer,
        request_id: str,
        address_id: str,
        *,
        scene_id: str | None = None,
        guide_destination_id: str | None = None,
        lead_fact_id: str | None = None,
    ) -> str:
        request_id, address_id = fact_identity(request_id), fact_identity(address_id)
        if lead_fact_id is not None:
            lead_fact_id = fact_identity(lead_fact_id)
            if guide_destination_id is not None:
                raise WorkflowError("Choose a guide offer or a private lead for this draft.")
        key = f"activity.ai-npc-reaction:{viewer.user_id}:{request_id}"

        def authorize(c: Connection) -> None:
            self.canon._access(c, viewer)
            self.canon.handler.authorize(c, viewer)

        def operation(c: Connection) -> dict[str, str]:
            policy = self._policy()
            self.missions.access.authorize(c, viewer, "world")
            scene, _, npc = self._source(c, viewer, address_id, viewer.user_id)
            if scene_id is not None and scene.window.scene_id != scene_id:
                raise WorkflowError("This NPC address is unavailable in this scene.")
            guide = (
                self._destinations(scene.state).get(guide_destination_id)
                if guide_destination_id is not None
                else None
            )
            if guide_destination_id is not None and guide is None:
                raise WorkflowError("Choose an operational destination from the campaign map.")
            if c.scalar(self._published_from(address_id).with_only_columns(t.events.c.id).limit(1)):
                raise WorkflowError("A facilitator already approved a reply to this address.")
            lead = self._lead(c, scene, npc, lead_fact_id) if lead_fact_id else None
            request = ReactionRequest(
                address_id=address_id,
                window=scene.window,
                game_revision=scene.state.revision,
                model=policy.model,
                prompt_version=PROMPT_VERSION,
                guide=guide,
                lead=lead,
            )
            request = request.model_copy(update={"prompt_version": request.expected_prompt})
            return {"id": self._audit(c, viewer, key, REQUESTED, request.model_dump(mode="json"))}

        result = self.store._write(
            viewer,
            key,
            REQUESTED,
            {"address_id": address_id}
            | ({"scene": scene_id} if scene_id is not None else {})
            | (
                {"guide_destination_id": guide_destination_id}
                if guide_destination_id is not None
                else {}
            )
            | ({"lead_fact_id": lead_fact_id} if lead_fact_id is not None else {}),
            operation,
            authorize=authorize,
            auto_audit=False,
        )
        return cast(str, result["id"])

    def _latest(self, c: Connection, identity: str) -> RowMapping | None:
        return (
            c.execute(
                calendar.query(self.campaign, REACTION_RESERVATION, RESULT, REVIEW)
                .where(sa.func.json_extract(t.events.c.payload_json, "$.request_id") == identity)
                .order_by(t.events.c.seq.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )

    def _view(
        self,
        c: Connection,
        identity: str,
        request: ReactionRequest,
        latest: RowMapping | None,
    ) -> dict[str, Any]:
        view: dict[str, Any] = {
            "id": identity,
            "address_id": request.address_id,
            "scene": request.window.scene_id,
            "status": "queued",
            "model": request.model,
            "prompt_version": request.prompt_version,
        }
        if request.guide is not None:
            view["guide"] = request.guide.model_dump(mode="json")
        if request.lead is not None:
            view["lead"] = {
                "fact_id": request.lead.fact_id,
                "statement": request.lead.statement,
            }
        if latest is None:
            return view
        payload = json.loads(latest["payload_json"])
        if latest["kind"] == REACTION_RESERVATION:
            over = self.store.clock() >= payload["expires_at"]
            return view | {"status": "interrupted" if over else "running"}
        if latest["kind"] == REVIEW:
            original = self._row(c, RESULT, payload["result_id"])
            reviewed = view | {
                "status": payload["status"],
                "reaction_id": payload["reaction_id"],
                "proposal": (
                    {"speech": payload["edited_speech"]}
                    if "edited_speech" in payload
                    else json.loads(original["payload_json"])["proposal"]
                ),
            }
            if request.guide is not None and payload["reaction_id"] is not None:
                counts = {"follow": 0, "decline": 0}
                for raw in c.scalars(
                    self._guide_responses(payload["reaction_id"]).with_only_columns(
                        t.events.c.payload_json
                    )
                ):
                    counts[json.loads(raw)["choice"]] += 1
                reviewed["guide_responses"] = counts
                if handoff := self._handoff(c, payload["reaction_id"]):
                    reviewed["handoff"] = handoff
            return reviewed
        return (
            view
            | {"status": payload["status"], "result_id": latest["id"]}
            | {key: payload[key] for key in ("proposal", "error") if key in payload}
        )

    def _review_audience(
        self, c: Connection, scene: LiveScene, source: Address, request: ReactionRequest
    ) -> dict[str, str]:
        if request.lead is not None:
            recipient = self._row(c, ADDRESSED, request.address_id)["actor_id"]
            return {recipient: source.speaker}
        return {
            str(owner): principal
            for owner in scene.participants
            if self.canon.handler._member(c, owner)
            and (principal := self.canon.principal(c, owner)) is not None
        }

    def _review_view(self, c: Connection, viewer: GuildViewer, row: RowMapping) -> dict[str, Any]:
        request = ReactionRequest.model_validate_json(row["payload_json"])
        view = self._view(c, row["id"], request, self._latest(c, row["id"]))
        if viewer.user_id != self.store.policy.canon_facilitator_id or view["status"] != "ready":
            return view
        fresh = self._unchanged(c, viewer, request, int(row["actor_id"]))
        if fresh is None:
            return view | {"review_unavailable": True}
        scene, source, _ = fresh
        audience = self._review_audience(c, scene, source, request)
        return view | {
            "review_audience": {
                "kind": "private_lead" if request.lead else "scene_cast",
                "receipt": _digest(audience),
                "listeners": [
                    "Handler"
                    if principal.startswith("handler:")
                    else sheet.callsign
                    if (sheet := scene.state.sheets.get(owner))
                    else "Pilot"
                    for owner, principal in sorted(audience.items())
                ],
            },
        }

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        identity = fact_identity(identity)
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            facilitator = viewer.user_id == self.store.policy.canon_facilitator_id
            self.canon._access(c, viewer, facilitator=facilitator)
            row = self._row(c, REQUESTED, identity)
            if not facilitator and (
                row["actor_id"] != str(viewer.user_id)
                or viewer.user_id != self.canon.handler.current(c)[1].handler_id
            ):
                raise WorkflowError("This NPC reaction request is unavailable.")
            return self._review_view(c, viewer, row)

    def list_requests(self, viewer: GuildViewer, scene_id: str) -> list[dict[str, Any]]:
        scene_id = fact_identity(scene_id)
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            facilitator = viewer.user_id == self.store.policy.canon_facilitator_id
            self.canon._access(c, viewer, facilitator=facilitator)
            query = calendar.query(self.campaign, REQUESTED).where(
                sa.func.json_extract(t.events.c.payload_json, "$.window.scene_id") == scene_id
            )
            if not facilitator:
                self.canon.handler.authorize(c, viewer)
                query = query.where(t.events.c.actor_id == str(viewer.user_id))
            return [
                self._review_view(c, viewer, row)
                for row in c.execute(query.order_by(t.events.c.seq.desc()).limit(25)).mappings()
            ]

    def _unchanged(
        self,
        c: Connection,
        viewer: GuildViewer,
        request: ReactionRequest,
        owner: int,
    ) -> tuple[LiveScene, Address, Npc] | None:
        try:
            scene, source, npc = self._source(c, viewer, request.address_id, owner)
            if (
                request.lead is not None
                and self._lead(c, scene, npc, request.lead.fact_id) != request.lead
            ):
                return None
        except WorkflowError:
            return None
        if (
            scene.state.revision != request.game_revision
            or scene.window != request.window
            or request.prompt_version != request.expected_prompt
            or (
                request.guide is not None
                and self._destinations(scene.state).get(request.guide.id) != request.guide
            )
            or c.scalar(
                self._published_from(request.address_id).with_only_columns(t.events.c.id).limit(1)
            )
        ):
            return None
        return scene, source, npc

    def _result(
        self,
        c: Connection,
        viewer: GuildViewer,
        identity: str,
        request: ReactionRequest,
        status: Literal["ready", "failed", "stale", "needs_ruling"],
        *,
        result: NpcReactionResult | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"request_id": identity, "status": status}
        if result is not None:
            body.update(result.model_dump(mode="json", exclude={"proposal"}))
            if status == "ready":
                body["proposal"] = result.proposal.model_dump(mode="json")
        if error is not None:
            body["error"] = error
        self._audit(c, viewer, f"ai-npc-reaction.result:{identity}", RESULT, body)
        return self._view(c, identity, request, self._latest(c, identity))

    def run(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        identity = fact_identity(identity)
        with self.store.transaction() as c:
            policy = self._policy()
            self.canon._access(c, viewer)
            self.canon.handler.authorize(c, viewer)
            row = self._row(c, REQUESTED, identity)
            if row["actor_id"] != str(viewer.user_id):
                raise WorkflowError("Only the requesting Handler can generate this NPC reaction.")
            request = ReactionRequest.model_validate_json(row["payload_json"])
            latest = self._latest(c, identity)
            if latest is not None:
                return self._view(c, identity, request, latest)
            self.missions.access.authorize(c, viewer, "world")
            self.canon.game.unpaused(c)
            self.canon.game.scene_unpaused(c, request.window.scene_id)
            fresh = self._unchanged(c, viewer, request, viewer.user_id)
            if fresh is None or policy.model != request.model:
                return self._result(c, viewer, identity, request, "stale")
            scene, source, npc = fresh
            from girlframe.services.director_dossiers import DirectorDossierService

            history = DirectorDossierService._records(
                scene.state, ActorRef(kind="npc", entity=npc.id)
            )
            manner = None
            if history and history[-1].controller == npc.controller:
                manner = history[-1].personnel.mannerisms.strip() or None
            attempt = reserve_attempt(
                c,
                self.store,
                viewer,
                identity,
                policy,
                kind=REACTION_RESERVATION,
                key=f"ai-npc-reaction.reserve:{identity}",
                prompt_version=request.prompt_version,
            )

        result = None
        failure = None
        try:
            result = self.gateway.generate(
                request.model,
                NpcReactionContext(
                    npc_name=npc.name,
                    address=source.statement,
                    public_manner=manner,
                    guide_destination=request.guide.name if request.guide is not None else None,
                    lead_fact=request.lead.statement if request.lead is not None else None,
                ),
                identity,
            )
        except ProviderError as error:
            failure = error.code

        with self.store.transaction() as c:
            latest = self._latest(c, identity)
            if latest is None or latest["id"] != attempt:
                return self._view(c, identity, request, latest)
            if self.store.clock() >= json.loads(latest["payload_json"])["expires_at"]:
                return self._view(c, identity, request, latest)
            if self._unchanged(c, viewer, request, viewer.user_id) is None:
                return self._result(c, viewer, identity, request, "stale", result=result)
            if failure is not None:
                return self._result(c, viewer, identity, request, "failed", error=failure)
            assert result is not None
            status: Literal["ready", "needs_ruling"] = (
                "ready" if result.proposal.speech is not None else "needs_ruling"
            )
            return self._result(c, viewer, identity, request, status, result=result)

    def review(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        result_id: str,
        *,
        approve: bool,
        edited_speech: str | None = None,
        expected_audience: str | None = None,
    ) -> dict[str, Any]:
        identity, result_id = fact_identity(identity), fact_identity(result_id)
        if edited_speech is not None:
            if not approve or expected_audience is None:
                raise WorkflowError("Preview the audience before approving an edited line.")
            try:
                NpcReactionText(speech=edited_speech)
            except ValidationError:
                raise WorkflowError("Use one printable line of in-character speech.") from None

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, REQUESTED, identity)
            request = ReactionRequest.model_validate_json(row["payload_json"])
            latest = self._latest(c, identity)
            if latest is None or latest["id"] != result_id or latest["kind"] != RESULT:
                raise WorkflowError("STALE_REACTION: reopen this exact proposal before reviewing.")
            data = json.loads(latest["payload_json"])
            if data["status"] != "ready":
                raise WorkflowError("Only a ready NPC reply can be reviewed.")
            reaction_id = None
            if approve:
                self.canon.game.unpaused(c)
                self.canon.game.scene_unpaused(c, request.window.scene_id)
                fresh = self._unchanged(c, viewer, request, int(row["actor_id"]))
                if fresh is None:
                    raise WorkflowError("STALE_REACTION: the source scene or NPC changed.")
                scene, source, npc = fresh
                proposal = NpcReactionText.model_validate(data["proposal"])
                if proposal.speech is None:
                    raise WorkflowError("This address needs a manual ruling.")
                speech = proposal.speech if edited_speech is None else edited_speech
                if RULES_IN_PROSE.search(speech):
                    raise WorkflowError("Keep rules and mechanical effects in the native controls.")
                audience = self._review_audience(c, scene, source, request)
                if expected_audience is not None and expected_audience != _digest(audience):
                    raise WorkflowError("STALE_AUDIENCE: preview the current listeners again.")
                if request.lead is not None:
                    recipient = int(self._row(c, ADDRESSED, request.address_id)["actor_id"])
                    self.canon.save_grant(
                        c,
                        viewer,
                        key,
                        KnowledgeGrant(
                            window=scene.window,
                            fact_id=request.lead.fact_id,
                            recipient=recipient,
                            method="told",
                            source_grant_id=request.lead.witness_id,
                            principal=source.speaker,
                        ),
                        index=2,
                    )
                reaction_id = str(uuid4())
                self._audit(
                    c,
                    viewer,
                    key,
                    PUBLISHED,
                    {
                        "scene": scene.window.scene_id,
                        "position": scene.window.position.model_dump(mode="json"),
                        "address_id": request.address_id,
                        "result_id": result_id,
                        "npc_id": npc.id,
                        "npc_name": npc.name,
                        "speech": speech,
                        "audience": audience,
                    }
                    | (
                        {
                            "guide": request.guide.model_dump(mode="json"),
                            "anchor_id": scene.window.anchor_id,
                            "controller": npc.controller,
                        }
                        if request.guide is not None
                        else {}
                    )
                    | ({"lead_fact_id": request.lead.fact_id} if request.lead is not None else {}),
                    event_id=reaction_id,
                    event_index=1,
                )
            self._audit(
                c,
                viewer,
                key,
                REVIEW,
                {
                    "request_id": identity,
                    "result_id": result_id,
                    "status": "approved" if approve else "declined",
                    "reaction_id": reaction_id,
                    **({"edited_speech": edited_speech} if edited_speech is not None else {}),
                },
            )
            return self._view(c, identity, request, self._latest(c, identity))

        return self.store._write(
            viewer,
            key,
            REVIEW,
            {
                "request": identity,
                "result": result_id,
                "approve": approve,
                **({"edited_speech": edited_speech} if edited_speech is not None else {}),
                **(
                    {"expected_audience": expected_audience}
                    if expected_audience is not None
                    else {}
                ),
            },
            operation,
            authorize=lambda c: self.canon._access(c, viewer, facilitator=True),
            auto_audit=False,
        )

    def _guide_responses(self, reaction_id: str) -> Select[Any]:
        return calendar.query(self.campaign, GUIDE_RESPONSE).where(
            sa.func.json_extract(t.events.c.payload_json, "$.reaction_id") == reaction_id,
        )

    def _handoff(self, c: Connection, reaction_id: str) -> dict[str, Any] | None:
        raw = c.scalar(
            calendar.query(self.campaign, GUIDE_HANDOFF)
            .where(sa.func.json_extract(t.events.c.payload_json, "$.reaction_id") == reaction_id)
            .with_only_columns(t.events.c.payload_json)
            .limit(1)
        )
        return cast(dict[str, Any], json.loads(raw)) if raw else None

    def guide_bookings(self, viewer: GuildViewer, scene_id: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.timeline._handler(c, viewer)
            scene = self._live(c, viewer, scene_id)
            rows = self.timeline._scene_rows(c)
            booked = self.timeline._scenes(c, rows)
            return {
                "position": scene.window.position.model_dump(mode="json"),
                "slots": SLOTS,
                "scenes": [
                    {"id": identity, "channel": row["channel_id"], "revision": row["revision"]}
                    for identity, row in rows.items()
                    if row["open"] and identity not in booked
                ],
            }

    def book_guide(
        self,
        viewer: GuildViewer,
        submission_id: str,
        scene_id: str,
        reaction_id: str,
        destination_scene_id: str,
        destination_revision: int,
        position: Position,
    ) -> dict[str, Any]:
        key = f"activity.guide-handoff:{viewer.user_id}:{submission_id}"

        def authorize(c: Connection) -> None:
            self.timeline._handler(c, viewer)
            self.canon._access(c, viewer)
            offer = json.loads(self._row(c, PUBLISHED, reaction_id)["payload_json"])
            if (
                offer["scene"] != scene_id
                or offer.get("guide") is None
                or offer.get("controller") != viewer.user_id
            ):
                raise WorkflowError("This guide offer is unavailable to the current Handler.")

        def operation(c: Connection) -> dict[str, Any]:
            if self._handoff(c, reaction_id) is not None:
                raise WorkflowError("This guide continuation is already booked.")
            offer = json.loads(self._row(c, PUBLISHED, reaction_id)["payload_json"])
            scene = self._live(c, viewer, scene_id)
            if not self._guide_open(scene, offer):
                raise WorkflowError("STALE_GUIDE: the scene, NPC, or destination changed.")
            if position.order <= scene.window.position.order:
                raise WorkflowError("Choose a future fictional slot for the guide continuation.")
            followers: dict[int, str] = {}
            responses = self._guide_responses(reaction_id).where(
                sa.func.json_extract(t.events.c.payload_json, "$.choice") == "follow"
            )
            for row in c.execute(responses.order_by(t.events.c.seq)).mappings():
                pilot = int(row["actor_id"])
                try:
                    principal = self._pilot(c, scene, pilot)
                except WorkflowError:
                    continue
                if principal == json.loads(row["payload_json"])["pilot"]:
                    followers[pilot] = principal.removeprefix("pilot:")
            if not followers:
                raise WorkflowError("At least one currently eligible Pilot must choose Follow.")
            bindings = {str(owner): incarnation for owner, incarnation in followers.items()}
            booking = self.timeline._schedule(
                c,
                viewer,
                key,
                self.canon._channel(c, destination_scene_id),
                destination_scene_id,
                destination_revision,
                scene.window.anchor_id,
                ScenePlan(
                    start=position,
                    end=position,
                    participants=tuple(followers),
                    location=offer["guide"]["name"],
                    pilot_bindings=bindings,
                ),
                unbooked=True,
            )
            body = {
                "reaction_id": reaction_id,
                "scene": destination_scene_id,
                "location": offer["guide"]["name"],
                "position": position.model_dump(mode="json"),
                "booking_receipt": booking["receipt"],
                "followers": len(followers),
            }
            return body | {"id": self._audit(c, viewer, key, GUIDE_HANDOFF, body, event_index=1)}

        return self.store._write(
            viewer,
            key,
            GUIDE_HANDOFF,
            {
                "scene": scene_id,
                "reaction_id": reaction_id,
                "destination_scene": destination_scene_id,
                "destination_revision": destination_revision,
                "position": position.model_dump(mode="json"),
            },
            operation,
            authorize=authorize,
            auto_audit=False,
        )

    def _guide_open(self, scene: LiveScene, offer: dict[str, Any]) -> bool:
        npc = scene.npcs.get(offer["npc_id"])
        destination = self._destinations(scene.state).get(offer["guide"]["id"])
        return (
            npc is not None
            and npc.controller == offer["controller"]
            and scene.window.anchor_id == offer["anchor_id"]
            and destination is not None
            and destination.name == offer["guide"]["name"]
        )

    def respond_to_guide(
        self,
        viewer: GuildViewer,
        response_id: str,
        scene_id: str,
        reaction_id: str,
        choice: GuideChoice,
    ) -> dict[str, Any]:
        response_id, scene_id, reaction_id = map(
            fact_identity, (response_id, scene_id, reaction_id)
        )
        if choice not in ("follow", "decline"):
            raise WorkflowError("Choose Follow or Decline for your Pilot.")
        key = f"activity.guide-response:{viewer.user_id}:{response_id}"

        def authorize(c: Connection) -> None:
            self.canon._access(c, viewer)
            data = json.loads(self._row(c, PUBLISHED, reaction_id)["payload_json"])
            principal = self.canon.principal(c, viewer.user_id)
            if (
                data["scene"] != scene_id
                or not data.get("guide")
                or principal is None
                or not principal.startswith("pilot:")
                or data["audience"].get(str(viewer.user_id)) != principal
            ):
                raise WorkflowError("This guide offer is unavailable to your Pilot.")

        def operation(c: Connection) -> dict[str, Any]:
            data = json.loads(self._row(c, PUBLISHED, reaction_id)["payload_json"])
            scene = self._live(c, viewer, scene_id)
            principal = self._pilot(c, scene, viewer.user_id)
            if self._handoff(c, reaction_id) is not None:
                raise WorkflowError("This guide continuation is already booked.")
            if not self._guide_open(scene, data):
                raise WorkflowError("STALE_GUIDE: the scene, NPC, or destination changed.")
            existing = self._guide_responses(reaction_id).where(
                t.events.c.actor_id == str(viewer.user_id),
                sa.func.json_extract(t.events.c.payload_json, "$.pilot") == principal,
            )
            if c.scalar(existing.with_only_columns(t.events.c.id).limit(1)) is not None:
                raise WorkflowError("Your Pilot already answered this guide offer.")
            receipt = self._audit(
                c,
                viewer,
                key,
                GUIDE_RESPONSE,
                {"reaction_id": reaction_id, "choice": choice, "pilot": principal},
            )
            return {"id": receipt, "choice": choice}

        return self.store._write(
            viewer,
            key,
            GUIDE_RESPONSE,
            {"scene": scene_id, "reaction_id": reaction_id, "choice": choice},
            operation,
            authorize=authorize,
            auto_audit=False,
        )

    def scene_feed(self, viewer: GuildViewer, scene_id: str) -> list[dict[str, Any]]:
        scene_id = fact_identity(scene_id)
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.canon._access(c, viewer)
            principal = self.canon.principal(c, viewer.user_id)
            if principal is None:
                return []
            query = calendar.query(self.campaign, PUBLISHED).where(
                sa.func.json_extract(t.events.c.payload_json, "$.scene") == scene_id,
                sa.func.json_extract(t.events.c.payload_json, f'$.audience."{viewer.user_id}"')
                == principal,
            )
            rows = c.execute(query.order_by(t.events.c.seq)).mappings().all()
            records = []
            live: LiveScene | None = None
            if principal.startswith("pilot:") and any(
                json.loads(row["payload_json"]).get("guide") for row in rows
            ):
                try:
                    live = self._live(c, viewer, scene_id)
                    self._pilot(c, live, viewer.user_id)
                except WorkflowError:
                    live = None
            for row in rows:
                data = json.loads(row["payload_json"])
                entry = {
                    "id": row["id"],
                    "recorded_utc": row["created_utc"],
                    **{
                        key: data[key]
                        for key in ("scene", "position", "npc_id", "npc_name", "speech")
                    },
                }
                if fact_id := data.get("lead_fact_id"):
                    entry["lead"] = {
                        "fact_id": fact_id,
                        "statement": self.canon._fact(c, fact_id).statement,
                    }
                if guide := data.get("guide"):
                    response = c.scalar(
                        self._guide_responses(row["id"])
                        .where(
                            t.events.c.actor_id == str(viewer.user_id),
                            sa.func.json_extract(t.events.c.payload_json, "$.pilot") == principal,
                        )
                        .with_only_columns(
                            sa.func.json_extract(t.events.c.payload_json, "$.choice")
                        )
                        .limit(1)
                    )
                    handoff = self._handoff(c, row["id"])
                    booked = (
                        calendar.booking(c, self.campaign, handoff["scene"])
                        if handoff is not None and response == "follow"
                        else None
                    )
                    entry["guide"] = guide | {
                        "response": response,
                        "open": live is not None
                        and response is None
                        and handoff is None
                        and self._guide_open(live, data),
                    }
                    if (
                        handoff is not None
                        and booked is not None
                        and booked.pilot_bindings.get(str(viewer.user_id))
                        == principal.removeprefix("pilot:")
                    ):
                        entry["guide"]["booking"] = {
                            "scene": handoff["scene"],
                            "position": booked.start.model_dump(mode="json"),
                        }
                records.append(entry)
            return records
