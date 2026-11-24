"""Role-scoped chances to act on an existing agenda without a dialogue trigger."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.ai.director_dossiers import DossierPacket, DossierPressure
from girlframe.ai.observation import Observation
from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole
from girlframe.engine.pilot_portrayal import PilotPortrayal
from girlframe.services.activity_dialogue import npc_owned
from girlframe.services.activity_scene_opening import ActivitySceneOpening
from girlframe.services.campaign_difficulty import opening
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_dossiers import DirectorDossierService
from girlframe.services.director_fronts import DirectorFrontService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.director_play_options import initiative_play_options
from girlframe.services.m2_state import load_state
from girlframe.services.m3_sentinel import require_communication
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ALTERNATE_REFERRALS = {
    "npc": (
        "Independent NPC Flirt",
        "The native NPC Flirt needs a Pilot's original Flirt or another typed producer. "
        "Independent NPC initiation has no native form.",
    ),
    "external_pilot": (
        "Masked Harpy Disobey Orders",
        "The Mask Order has no native Disobey continuation for this original Harpy body.",
    ),
    "gorgon": (
        "Gorgon Collateral Damage",
        "Independent initiative lacks the original threatened site, verified attacking "
        "capabilities and reach, and the saving-Play follow-up binding.",
    ),
}


class DirectorInitiative:
    def __init__(self, context: DirectorContextService):
        self.context = context
        self.observer = context.observations
        self.store = context.store
        self.knowledge = DirectorKnowledgeService(context)
        self.dossiers = DirectorDossierService(context)
        self.fronts = DirectorFrontService(context)

    def _alternate_roles(self, c: Connection, row: dict[str, Any]) -> dict[ActorRef, CastRole]:
        state = load_state(c, self.store.campaign_id)
        cast = next((x for x in state.scene_casts if x.id == row["id"] and x.open), None)
        if cast is None:
            return {}
        actual = {x.ref: x for x in self.knowledge._actor_views(c, row)}
        return {
            role.actor: role
            for role in cast.roles
            if role.actor in actual
            and role.controller == actual[role.actor].controller
            and (
                role.actor.kind == "gorgon"
                or role.actor.kind == "npc"
                and actual[role.actor].rules == "npc"
                or role.actor.kind == "external_pilot"
                and actual[role.actor].girl == "harpy"
            )
        }

    def _control(self, c: Connection, scene: str, actor: ActorRef) -> dict[str, Any]:
        events = t.events
        row = c.execute(
            sa.select(events.c.id, events.c.actor_id, events.c.payload_json)
            .where(
                events.c.campaign_id == self.store.campaign_id,
                events.c.kind == "director.alternate_control_changed",
                sa.func.json_extract(events.c.payload_json, "$.scene") == scene,
                sa.func.json_extract(events.c.payload_json, "$.actor") == actor.token,
            )
            .order_by(events.c.seq.desc())
            .limit(1)
        ).first()
        if row is None:
            return {}
        payload: dict[str, Any] = json.loads(row.payload_json)
        return payload | {"controller": int(row.actor_id), "event": row.id}

    def _delegated(self, c: Connection, row: dict[str, Any], role: CastRole) -> str | None:
        current = self._control(c, row["id"], role.actor)
        if (
            current.get("enabled")
            and current.get("controller") == role.controller
            and current.get("cast_source") == role.source_event
        ):
            return str(current["event"])
        return None

    def alternate_controls(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            row = self.observer._scene(c, scene, viewer)
            roles = self._alternate_roles(c, row)
            state = self.observer._state(c, scene)
            consented = state.policy.mode == "shadow" and self.observer._consented(c, row, state)
            result = []
            for actor in self.knowledge._actor_views(c, row):
                if actor.ref not in roles or actor.controller != viewer.user_id:
                    continue
                enabled = bool(self._delegated(c, row, roles[actor.ref]))
                native = (
                    initiative_play_options(self.context, c, scene, actor.ref, alternate=True)
                    if enabled and consented
                    else ()
                )
                result.append(
                    dict(
                        actor=actor.ref.model_dump(mode="json"),
                        label=actor.label,
                        enabled=enabled,
                        revision=self._control(c, scene, actor.ref).get("event"),
                        referral=ALTERNATE_REFERRALS[actor.ref.kind][0],
                        plays=[
                            dict(
                                id=play["id"],
                                label=play["label"],
                                target=play["alternate"]["target_token"],
                                reach=play["alternate"]["reach"],
                                costs=play["alternate"]["costs"],
                                choices=play["alternate"]["choices"],
                            )
                            for play in native
                        ],
                    )
                )
            return result

    def control_alternate(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        actor: ActorRef,
        enabled: bool,
        revision: str | None,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.observer._scope()
            row = self.observer._scene(c, scene, viewer)
            role = self._alternate_roles(c, row).get(actor)
            if role is None or role.controller != viewer.user_id:
                raise WorkflowError("INITIATIVE_CONTROL_OWNER: choose your actual cast actor.")
            if enabled:
                self.observer.game.scene_unpaused(c, scene)
                state = self.observer._state(c, scene)
                if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
                    raise WorkflowError("OBSERVATION_DISABLED: current scene consent required.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self.observer._scene(c, scene, viewer)
            role = self._alternate_roles(c, row)[actor]
            if self._control(c, scene, actor).get("event") != revision:
                raise WorkflowError("INITIATIVE_CONTROL_STALE: reopen the current actor setting.")
            event = self.store._audit(
                c,
                viewer.user_id,
                key,
                "director.alternate_control_changed",
                dict(
                    scene=scene, actor=actor.token, enabled=enabled, cast_source=role.source_event
                ),
            )
            return {"enabled": enabled, "revision": event}

        return self.store._write(
            viewer,
            key,
            "director.alternate_control_changed",
            dict(scene=scene, actor=actor.token, enabled=enabled, revision=revision),
            operation,
            authorize=authorize,
            auto_audit=False,
        )

    def refer_alternate(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        actor: ActorRef,
    ) -> dict[str, Any]:
        from girlframe.services.p1_facilitator import UNLISTED_ACTION, FacilitatorService

        def scoped(c: Connection) -> tuple[int, int]:
            row = self.observer._scene(c, scene, viewer)
            state = self.observer._state(c, scene)
            role = self._alternate_roles(c, row).get(actor)
            if (
                role is None
                or role.controller != viewer.user_id
                or self._delegated(c, row, role) is None
            ):
                raise WorkflowError("INITIATIVE_CONTROL_OWNER: choose your actual cast actor.")
            if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
                raise WorkflowError("OBSERVATION_DISABLED: current scene consent required.")
            return int(row["channel_id"]), load_state(c, self.store.campaign_id).revision

        with self.store.engine.connect() as c:
            channel, revision = scoped(c)
        title, missing = ALTERNATE_REFERRALS[actor.kind]

        def guard(c: Connection) -> None:
            scoped(c)

        return FacilitatorService(self.observer.game).request(
            viewer,
            key,
            channel,
            "scene",
            scene,
            UNLISTED_ACTION,
            revision,
            f"{title} for {actor.token}. {missing}",
            shared=True,
            source_guard=guard,
        )

    def scope(self, c: Connection, viewer: GuildViewer, scene: str) -> None:
        self.knowledge._scope(c, viewer, scene)
        self.observer.game.scene_unpaused(c, scene)
        if self.observer.reviewed_activity_trial and (
            not viewer.activity_review or viewer.user_id != self.observer.facilitator(c)
        ):
            raise WorkflowError("INITIATIVE_REVIEW_OWNER: use the approved facilitator.")

    def _recent_comms(
        self, c: Connection, row: dict[str, Any], actors: tuple[ActorView, ...]
    ) -> tuple[Observation, ...]:
        table = t.director["inputs"]
        recent = self.observer._pending(row["id"], 0, include_handled=True).where(
            table.c.kind == "message",
            sa.func.json_extract(table.c.body_json, "$.fictional_channel") == "comms",
        )
        capture = {actor.ref.token: actor.controller for actor in actors}
        audience = tuple(sorted(str(uid) for uid in row["participants"]))
        sources = tuple(
            item
            for raw in c.scalars(
                recent.with_only_columns(table.c.body_json)
                .order_by(table.c.sequence.desc())
                .limit(20)
            )
            if (item := Observation.model_validate_json(raw)).cast_controllers == capture
            and item.audience_ids == audience
            and not item.gm_addressed
        )
        reserved = npc_owned(
            c, self.store.campaign_id, row["id"], tuple(item.source_id for item in sources)
        )
        return tuple(item for item in sources if item.source_id not in reserved)

    def _reply_source(
        self,
        c: Connection,
        scene: str,
        canon: GameState,
        actor: ActorRef,
        sources: tuple[Observation, ...],
    ) -> Observation | None:
        from girlframe.services.director_npc_delivery import NpcDeliveryService, heard_episode

        delivery = NpcDeliveryService(self.context)
        for source in sources:
            if source.actor == actor:
                continue
            episode = heard_episode(actor, source.source_id, source.source_revision)
            if delivery._record(c, scene, episode):
                # Keep the reply attached to this turn. An older turn does not regain the floor.
                return None
            try:
                require_communication(c, self.store.campaign_id, canon, source.actor, (actor,))
            except WorkflowError:
                continue
            return source
        return None

    def candidates(self, c: Connection, scene: str) -> list[dict[str, Any]]:
        row = self.observer._scene(c, scene)
        self.observer.game.scene_unpaused(c, scene)
        state = self.observer._state(c, scene)
        if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
            raise WorkflowError("OBSERVATION_DISABLED: current scene consent required.")
        approved = opening(c, self.store.campaign_id)
        if approved is None:
            return []
        framing = ActivitySceneOpening(self.context).current(c, row)
        pilots = self.dossiers.activity_pilots(c, scene)
        references = self.context._current(c, scene)
        native_guard = self.observer._guard(c, row, state)
        result = []
        alternate = self._alternate_roles(c, row)
        grants = {
            actor: grant
            for actor, role in alternate.items()
            if (grant := self._delegated(c, row, role)) is not None
        }
        actors = self.knowledge._actor_views(c, row)
        comms = (
            self._recent_comms(c, row, actors)
            if state.activity_epoch is not None
            and any(actor.kind in ("external_pilot", "gorgon") for actor in grants)
            else ()
        )
        canon = load_state(c, self.store.campaign_id) if grants else None
        for role in actors:
            actor = role.ref
            delegated = grants.get(actor)
            if delegated:
                plays = initiative_play_options(self.context, c, scene, actor, alternate=True)
                reply = (
                    self._reply_source(c, scene, canon, actor, comms)
                    if canon is not None and comms and actor.kind in ("external_pilot", "gorgon")
                    else None
                )
                if plays or reply:
                    dossier = self.dossiers._role_packet(
                        c, scene, actor, omit_stale_portrayal=True, activity_pilot=True
                    )
                    refs = self.context._actor_references(references, actor)
                    portrayal = dossier.profile.pilot_portrayal if dossier.profile else None
                    agendas = self._agendas(c, scene, dossier, refs, portrayal, "")
                    subject, agenda = next(iter(agendas), ("Act in the current scene", {}))
                    identity: dict[str, Any] = {"kind": actor.kind}
                    if actor.kind == "npc":
                        identity["jobs"] = list(role.jobs)
                    elif actor.kind == "external_pilot":
                        identity.update(kind="harpy", frame=role.frame)
                    elif canon and canon.world:
                        gorgon = next(x for x in canon.world.gorgons if x.id == actor.entity)
                        identity.update(gorgon_class=gorgon.gorgon_class, types=list(gorgon.types))
                    base = dict(
                        controller=str(role.controller),
                        dossier=dossier.model_dump(mode="json"),
                        references=[ref.model_dump(mode="json") for ref in refs],
                        agenda=agenda,
                        role_identity=identity,
                        native_guard=native_guard,
                        alternate=delegated,
                    )
                    if plays:
                        turn = plays[0]["alternate"]["turn"]
                        source_id = "native:" + _digest((scene, actor.token, delegated, turn))
                        result.append(
                            dict(
                                **base,
                                option=dict(
                                    id=_digest((source_id, "alternate")),
                                    actor=actor.model_dump(mode="json"),
                                    label=role.label,
                                    source=dict(kind="native", id=source_id),
                                    subject=subject,
                                ),
                                trigger={"kind": "current_turn" if turn else "current_scene"},
                                native_plays=plays,
                            )
                        )
                    if reply:
                        source = (actor.token, delegated, reply.source_id, reply.source_revision)
                        result.append(
                            dict(
                                **base,
                                option=dict(
                                    id=_digest(source),
                                    actor=actor.model_dump(mode="json"),
                                    label=role.label,
                                    source=dict(kind="comms", id=reply.source_id),
                                    subject="Comms reply",
                                    quote=reply.text,
                                ),
                                trigger={"kind": "heard_comms", "revision": reply.source_revision},
                            )
                        )
            pilot = pilots.get(actor)
            handler = (
                actor.kind == "handler"
                and approved.handler_control == "ai"
                and role.controller == approved.handler
            )
            if pilot is None and not handler:
                continue
            dossier = self.dossiers._role_packet(
                c, scene, actor, activity_pilot=pilot is not None, omit_stale_portrayal=True
            )
            refs = self.context._actor_references(references, actor)
            agendas = self._agendas(
                c,
                scene,
                dossier,
                refs,
                pilot[1] if pilot else None,
                approved.goals if handler else "",
            )
            for subject, agenda in agendas:
                sources = []
                if framing:
                    sources.append(("opening", framing.receipt, framing.model_dump(mode="json")))
                # An event must already be heard/known by this actor and linked to its agenda.
                event = next(
                    (
                        ref
                        for ref in reversed(refs)
                        if ref.id in agenda["evidence"]
                        and ref.classification
                        in ("committed_play", "approved_outcome", "established_world")
                    ),
                    None,
                )
                if event is not None:
                    sources.append(("event", event.id, event.model_dump(mode="json")))
                for kind, source_id, trigger in sources:
                    result.append(
                        {
                            "option": {
                                "id": _digest((actor.token, agenda, kind, source_id)),
                                "actor": actor.model_dump(mode="json"),
                                "label": pilot[0] if pilot is not None else "Handler",
                                "source": {"kind": kind, "id": source_id},
                                "subject": subject,
                            },
                            "controller": str(role.controller),
                            "dossier": dossier.model_dump(mode="json"),
                            "references": [ref.model_dump(mode="json") for ref in refs],
                            "agenda": agenda,
                            "trigger": trigger,
                            "native_guard": native_guard,
                        }
                    )
        return result

    def _agendas(
        self,
        c: Connection,
        scene: str,
        dossier: DossierPacket,
        references: tuple[KnowledgeReference, ...],
        portrayal: PilotPortrayal | None,
        handler_goals: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        visible = {ref.id for ref in references}
        pressures = dossier.state.pressures if dossier.state else ()
        active = [
            (
                "Unfinished agenda",
                {
                    "id": item.pressure_id,
                    "plan": item.pressure.model_dump(mode="json"),
                    "evidence": list(item.knowledge_refs),
                },
            )
            for item in pressures
            if isinstance(item, DossierPressure)
            and item.pressure.status == "open"
            and item.pressure.next_step
            and set(item.knowledge_refs) <= visible
        ]
        # The current pressure list supersedes a starting aim when one has been filed.
        setup = dossier.profile.character_setup if dossier.profile else None
        aim = (setup.drive if setup else "") or (portrayal.goal if portrayal else "")
        aim = aim or handler_goals
        if not pressures and aim.strip():
            active.append(
                (
                    "Standing objective",
                    {
                        "id": "standing_objective",
                        "plan": {"stake": aim},
                        "evidence": [],
                    },
                )
            )
        move = self.fronts.portrayal_move(c, scene, dossier.actor)
        if move is not None and set(move.source_refs) <= visible:
            active.append(
                (
                    "Front opportunity",
                    {
                        "id": move.id,
                        "plan": {"next_step": move.text},
                        "evidence": list(move.source_refs),
                    },
                )
            )
        return active

    def packet(self, c: Connection, scene: str, option: str) -> dict[str, Any]:
        candidate = next(
            (entry for entry in self.candidates(c, scene) if entry["option"]["id"] == option),
            None,
        )
        if candidate is None:
            raise WorkflowError("INITIATIVE_STALE: refresh the approved opening or event.")
        selected = candidate["option"]
        actor = ActorRef.model_validate(selected["actor"])
        dialogue = selected["source"]["kind"] == "comms"
        role = {
            "actor": selected["actor"],
            "label": selected["label"],
            "dossier": candidate["dossier"],
            "references": candidate["references"],
            "initiative": {
                "source": selected["source"],
                "trigger": candidate["trigger"],
                "agenda": candidate["agenda"],
            },
            "available_actions": ["WAIT", "DIALOGUE" if dialogue else "SCENE_OFFER"],
            **({"identity": candidate["role_identity"]} if candidate.get("alternate") else {}),
            "native_plays": list(
                ()
                if dialogue
                else candidate["native_plays"]
                if candidate.get("alternate")
                else initiative_play_options(self.context, c, scene, actor)
            ),
        }
        if dialogue:
            role["question"] = selected["quote"]
        revision = _digest((role, candidate["native_guard"]))
        return {
            "request_id": "reaction-initiative:" + _digest((option, revision)),
            "scene_id": scene,
            "source_id": selected["source"]["id"],
            "run_id": None,
            "actor": selected["actor"],
            "controller": candidate["controller"],
            "role": role,
            "revision": revision,
            "initiative": option,
            **(
                {"activity_alternate_dialogue": candidate["alternate"]}
                if dialogue
                else {"activity_alternate": candidate["alternate"]}
                if candidate.get("alternate")
                else {"activity_pilot": True}
                if actor.kind != "handler"
                else {}
            ),
        }
