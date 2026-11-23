"""Role-scoped chances to act on an existing agenda without a dialogue trigger."""

from typing import Any

from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.ai.director_dossiers import DossierPacket
from girlframe.engine.campaign_opening import PilotPortrayal
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.activity_scene_opening import ActivitySceneOpening
from girlframe.services.campaign_difficulty import opening
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_dossiers import DirectorDossierService
from girlframe.services.director_fronts import DirectorFrontService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorInitiative:
    def __init__(self, context: DirectorContextService):
        self.context = context
        self.observer = context.observations
        self.store = context.store
        self.knowledge = DirectorKnowledgeService(context)
        self.dossiers = DirectorDossierService(context)
        self.fronts = DirectorFrontService(context)

    def scope(self, c: Connection, viewer: GuildViewer, scene: str) -> None:
        self.knowledge._scope(c, viewer, scene)
        self.observer.game.scene_unpaused(c, scene)
        if self.observer.reviewed_activity_trial and (
            not viewer.activity_review or viewer.user_id != self.observer.facilitator(c)
        ):
            raise WorkflowError("INITIATIVE_REVIEW_OWNER: use the approved facilitator.")

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
        for role in self.knowledge._actor_views(c, row):
            actor = role.ref
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
                c, scene, dossier, refs, pilot, approved.goals if handler else ""
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
        pilot: tuple[str, PilotPortrayal | None] | None,
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
            if item.pressure.status == "open"
            and item.pressure.next_step
            and set(item.knowledge_refs) <= visible
        ]
        # The current pressure list supersedes a starting aim when one has been filed.
        setup = dossier.profile.character_setup if dossier.profile else None
        aim = (setup.drive if setup else "") or (pilot[1].goal if pilot and pilot[1] else "")
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
        from girlframe.services.director_play_options import initiative_play_options

        candidate = next(
            (entry for entry in self.candidates(c, scene) if entry["option"]["id"] == option),
            None,
        )
        if candidate is None:
            raise WorkflowError("INITIATIVE_STALE: refresh the approved opening or event.")
        selected = candidate["option"]
        actor = ActorRef.model_validate(selected["actor"])
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
            "available_actions": ["WAIT", "SCENE_OFFER"],
            "native_plays": list(initiative_play_options(self.context, c, scene, actor)),
        }
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
            **({"activity_pilot": True} if actor.kind != "handler" else {}),
        }
