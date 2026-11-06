"""Genuine acquired Deep-Brain-Spikes, real memory scenes and source-owned return."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_deep_brain_spikes as rules
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_pr import _audit
from girlframe.services.m3_scene_requisitions import privacy
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    value = next((x for x in rules.acquisitions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the genuine original Deep-Brain-Spikes acquisition")
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    born = next(
        (x for x in rules.acquisitions(_history(c, game, value.event)) if x.id == identity), None
    )
    _, _, handler, appointment, award = HandlerAdvancementService(game.store)._proof(c, value.award)
    if (
        born != value
        or award is None
        or award.acquired_rule != rules.RULE
        or award.acquisition != value.id
        or award.spend_event != value.event
        or (handler, appointment) != (value.handler, value.appointment)
    ):
        raise WorkflowError("Recover the exact original held award and actual acquisition spend")
    return value


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Memory:
    value = next((x for x in rules.memories(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover this exact actual played-memory scene")
    receipt = paid(game, c, state, value.acquisition)
    initial = _history(c, game, value.event)
    born = next((x for x in rules.memories(initial) if x.id == identity), None)
    _audit(game, c, value.event, "m3.deep_brain_spikes_started", receipt.handler.entity)
    if (
        born is None
        or born.phase != "active"
        or born.handler != receipt.handler
        or value.handler != receipt.handler
        or value.appointment != receipt.appointment
        or any(
            getattr(born, k) != getattr(value, k)
            for k in (
                "id",
                "acquisition",
                "handler",
                "appointment",
                "subject",
                "mode",
                "period",
                "beginning",
                "circumstances",
                "channel",
                "scene",
                "present_scene",
                "present_revision",
                "present_cast",
                "participants",
                "event",
                "tag_uses",
            )
        )
        or value.scene == value.present_scene
        or not any(x.id == value.scene and x.open for x in initial.scene_casts)
    ):
        raise WorkflowError("Preserve the actual original memory, current cast and saved present")
    for entry in value.contributions:
        recorded = next(
            (x for x in rules.memories(_history(c, game, entry.event)) if x.id == identity), None
        )
        _audit(game, c, entry.event, "m3.deep_brain_spikes_contributed", entry.actor.entity)
        if recorded is None or entry not in recorded.contributions:
            raise WorkflowError(
                "Recover each actual original participant's remembered scene contribution"
            )
        if entry.action:
            action = game.action(c, entry.action)
            if (
                action["state"] != "complete"
                or action["scene_id"] != value.scene
                or action["actor_id"] != entry.actor.entity
                or action["data"].get("character_ids", {}).get(entry.actor.entity)
                != entry.actor.incarnation
            ):
                raise WorkflowError(
                    "A linked Play must be this actual current actor's completed memory-scene Play"
                )
    if value.phase == "returned":
        returned = _history(c, game, value.return_event or "")
        saved = next((x for x in rules.memories(returned) if x.id == identity), None)
        _audit(
            game,
            c,
            value.return_event or "",
            "m3.deep_brain_spikes_returned",
            receipt.handler.entity,
        )
        if (
            saved != value
            or not value.return_account
            or value.return_cause is None
            or not any(x.id == value.present_scene and x.open for x in returned.scene_casts)
            or any(x.id == value.scene and x.open for x in returned.scene_casts)
        ):
            raise WorkflowError("Recover actual source-owned return to the saved present context")
    return value


def _idle(game: GameService, c: Connection, scene: str, channel: int) -> None:
    lock = game.lock(c, channel)
    if lock and lock["state"] != "released":
        raise WorkflowError("Restore actual chat permissions before switching scene context")
    actions = list(
        c.execute(
            sa.select(t.m2["m2_actions"]).where(
                t.m2["m2_actions"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_actions"].c.scene_id == scene,
            )
        ).mappings()
    )
    for action in actions:
        data = json.loads(action["body_json"])
        if action["state"] not in ("complete", "aborted") or (
            action["state"] == "aborted"
            and (
                data.get("shared_recovery")
                or data.get("receipt")
                and (data.get("m3_recovery") or data.get("actor_recovery"))
            )
        ):
            raise WorkflowError("Finish or recover this scene's actual pending Play first")
    work = t.m3["m3_required_work"]
    latest = {
        x["id"]: x
        for x in c.execute(
            sa.select(work)
            .where(work.c.campaign_id == game.store.campaign_id)
            .order_by(work.c.revision)
        ).mappings()
    }
    if any(x["scene_id"] == scene and x["state"] != "resolved" for x in latest.values()):
        raise WorkflowError("Resolve the actual source-bound scene consequences before returning")


class DeepBrainSpikesService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy", director_response=True)
        gate.authorize(c, viewer, "playbooks", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, payload: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                payload,
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def buy(
        self, viewer: GuildViewer, key: str, award_id: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _, state, handler, appointment, award = HandlerAdvancementService(self.store)._source(
                c, viewer, award_id
            )
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            if (
                state.revision != revision
                or award is None
                or award.phase != "held"
                or not account.strip()
                or any(same_handler_body(state, x.handler) for x in rules.acquisitions(state))
            ):
                raise WorkflowError("Spend one actual held award on unowned Deep-Brain-Spikes")
            event = str(uuid4())
            value = rules.Acquisition(
                id="deep-brain-spikes:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            advancement.put(
                state,
                advancement.Award.model_validate_json(
                    award.model_copy(
                        update=dict(
                            phase="spent",
                            acquired_rule=rules.RULE,
                            acquisition=value.id,
                            spend_event=event,
                            spend_account=account.strip(),
                        )
                    ).model_dump_json()
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
            )
            return dict(id=value.id, phase="held")

        return self._write(
            viewer,
            key,
            "m3.deep_brain_spikes_acquired",
            dict(award=award_id, revision=revision, account=account),
            operation,
        )

    def begin(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        channel: int,
        subject: ActorRef,
        mode: Literal["there", "watching"],
        period: Literal["offscreen", "before_game"],
        beginning: str,
        circumstances: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            receipt = paid(self.game, c, state, acquisition)
            HandlerAdvancementService(self.store)._current(
                c, state, receipt.handler, receipt.appointment
            )
            if viewer.user_id != int(receipt.handler.entity) or state.revision != revision:
                raise WorkflowError(
                    "Only the actual original purchasing Handler sets the memory beginning"
                )
            scene = self.game.scene(c, channel)
            cast = _cast(self.game, c, state, channel)
            bindings = profiles(c, self.store.campaign_id)
            if (
                viewer.user_id not in scene["participants"]
                or subject.kind != "pilot"
                or not any(x.actor == subject for x in cast.roles)
                or subject != current_ref(state, int(subject.entity))
                or not beginning.strip()
                or not circumstances.strip()
            ):
                raise WorkflowError("Use an actual original Girl in this joined present scene")
            resolve(state, subject, bindings, require_current_profile=False)
            if privacy(c, self.store, scene["id"], history=True) is not None:
                raise WorkflowError(
                    "Finish the actual protected scene before opening a played memory"
                )
            if any(
                x.phase == "active" and (x.acquisition == acquisition or x.channel == channel)
                for x in rules.memories(state)
            ):
                raise WorkflowError("Return from this actual active memory before opening another")
            _idle(self.game, c, scene["id"], channel)
            event, identity, memory_scene = str(uuid4()), str(uuid4()), str(uuid4())
            value = rules.Memory(
                id=identity,
                acquisition=acquisition,
                handler=receipt.handler,
                appointment=receipt.appointment,
                subject=subject,
                mode=mode,
                period=period,
                beginning=beginning.strip(),
                circumstances=circumstances.strip(),
                channel=channel,
                scene=memory_scene,
                present_scene=scene["id"],
                present_revision=scene["revision"],
                present_cast=cast,
                participants=tuple(scene["participants"]),
                event=event,
                tag_uses=rules.saved_tag_uses(state, scene["id"]),
            )
            # One actual channel now routes to the memory context; no physical entity moves.
            state.scene_casts = [x for x in state.scene_casts if x.id != cast.id] + [
                cast.model_copy(update=dict(open=False, revision=cast.revision + 1)),
                cast.model_copy(
                    update=dict(
                        id=memory_scene,
                        revision=1,
                        open=True,
                        roles=tuple(
                            x.model_copy(update=dict(source_event=event)) for x in cast.roles
                        ),
                    )
                ),
            ]
            c.execute(
                t.m2["m2_scenes"]
                .update()
                .where(
                    t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_scenes"].c.channel_id == str(channel),
                )
                .values(id=memory_scene, revision=scene["revision"] + 1)
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.deep_brain_spikes_started",
                state,
                event_id=event,
                memory_id=identity,
                scene_id=memory_scene,
            )
            return dict(id=identity, phase="active", scene=memory_scene)

        return self._write(
            viewer,
            key,
            "m3.deep_brain_spikes_started",
            dict(
                acquisition=acquisition,
                revision=revision,
                channel=channel,
                subject=subject.model_dump(mode="json"),
                mode=mode,
                period=period,
                beginning=beginning,
                circumstances=circumstances,
            ),
            operation,
        )

    def _party(
        self, c: Connection, state: GameState, viewer: GuildViewer, value: rules.Memory
    ) -> None:
        if viewer.user_id in value.participants or any(
            entry.actor.entity == str(viewer.user_id) for entry in value.contributions
        ):
            return
        if value.phase == "active":
            cast = _cast(self.game, c, state, value.channel)
            if any(x.controller == viewer.user_id for x in cast.roles):
                return
        raise WorkflowError("This private memory belongs to its actual scene participants")

    def contribute(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
        action: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            self._party(c, state, viewer, value)
            scene = self.game.scene(c, value.channel)
            cast = _cast(self.game, c, state, value.channel)
            actor = current_ref(state, viewer.user_id)
            if (
                state.revision != revision
                or value.phase != "active"
                or scene["id"] != value.scene
                or not (
                    any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles)
                    or actor == value.handler
                    and cast.facilitator == viewer.user_id
                )
            ):
                raise WorkflowError(
                    "Only an actual current scene participant authors its speech/actions"
                )
            if action:
                actual = self.game.action(c, action)
                if (
                    actual["scene_id"] != value.scene
                    or actual["state"] != "complete"
                    or actual["actor_id"] != actor.entity
                    or actual["data"].get("character_ids", {}).get(actor.entity)
                    != actor.incarnation
                ):
                    raise WorkflowError(
                        "Link only your actual completed current-actor memory-scene Play"
                    )
            event = str(uuid4())
            contribution = rules.Contribution(
                event=event, actor=actor, account=account.strip(), action=action
            )
            value = value.model_copy(
                update=dict(contributions=value.contributions + (contribution,))
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.deep_brain_spikes_contributed",
                state,
                event_id=event,
                memory_id=identity,
            )
            return dict(id=identity, phase="active")

        return self._write(
            viewer,
            key,
            "m3.deep_brain_spikes_contributed",
            dict(id=identity, revision=revision, account=account, action=action),
            operation,
        )

    def return_present(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        cause: Literal["relevance_clear", "major_discrepancy"],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            receipt = paid(self.game, c, state, value.acquisition)
            HandlerAdvancementService(self.store)._current(
                c, state, receipt.handler, receipt.appointment
            )
            scene = self.game.scene(c, value.channel)
            if (
                viewer.user_id != int(value.handler.entity)
                or state.revision != revision
                or value.phase != "active"
                or scene["id"] != value.scene
                or cause not in ("relevance_clear", "major_discrepancy")
                or not account.strip()
            ):
                raise WorkflowError("Record this original Handler's actual printed return cause")
            _idle(self.game, c, value.scene, value.channel)
            present = next((x for x in state.scene_casts if x.id == value.present_scene), None)
            if present is None:
                raise WorkflowError("Recover the actual suspended present scene/cast source")
            event = str(uuid4())
            state.scene_casts = [
                x.model_copy(update=dict(open=False, revision=x.revision + 1))
                if x.id == value.scene
                else x.model_copy(update=dict(open=True, revision=x.revision + 1))
                if x.id == present.id
                else x
                for x in state.scene_casts
            ]
            c.execute(
                t.m2["m2_scenes"]
                .update()
                .where(
                    t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_scenes"].c.channel_id == str(value.channel),
                )
                .values(
                    id=value.present_scene,
                    revision=scene["revision"] + 1,
                    participants_json=json.dumps(value.participants),
                )
            )
            rules.restore_present_usage(state, value)
            value = value.model_copy(
                update=dict(
                    phase="returned",
                    return_cause=cause,
                    return_account=account.strip(),
                    return_event=event,
                )
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.deep_brain_spikes_returned",
                state,
                event_id=event,
                memory_id=identity,
                cause=cause,
            )
            return dict(id=identity, phase="returned", scene=value.present_scene)

        return self._write(
            viewer,
            key,
            "m3.deep_brain_spikes_returned",
            dict(id=identity, revision=revision, cause=cause, account=account),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            memory = next((x for x in rules.memories(state) if x.id == identity), None)
            if memory:
                value = source(self.game, c, state, memory.id)
                self._party(c, state, viewer, value)
                return value.model_dump(mode="json", exclude={"tag_uses", "present_cast"}) | dict(
                    revision=state.revision,
                    owner=viewer.user_id == int(value.handler.entity),
                    kind="memory",
                )
            receipts = [
                paid(self.game, c, state, x.id)
                for x in rules.acquisitions(state)
                if x.handler.entity == str(viewer.user_id)
                and (identity is None or x.id == identity)
            ]
            if identity and not receipts:
                raise WorkflowError(
                    "This actual advancement source belongs to another original Handler"
                )
            scenes = []
            if receipts:
                for row in c.execute(
                    sa.select(t.m2["m2_scenes"]).where(
                        t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_scenes"].c.open.is_(True),
                    )
                ).mappings():
                    if viewer.user_id not in json.loads(row["participants_json"]):
                        continue
                    cast = _cast(self.game, c, state, int(row["channel_id"]))
                    girls = [
                        dict(
                            ref=x.actor.model_dump(mode="json"),
                            token=x.actor.token,
                            label=resolve(
                                state,
                                x.actor,
                                profiles(c, self.store.campaign_id),
                                require_current_profile=False,
                            ).label,
                        )
                        for x in cast.roles
                        if x.actor.kind == "pilot"
                    ]
                    scenes.append(
                        dict(scene=row["id"], channel=int(row["channel_id"]), girls=girls)
                    )
            return dict(
                kind="acquisition",
                revision=state.revision,
                acquisition=receipts[0].id if receipts else None,
                scenes=scenes,
                active=[
                    dict(id=x.id, channel=x.channel)
                    for x in rules.memories(state)
                    if x.phase == "active" and x.handler.entity == str(viewer.user_id)
                ],
                awards=[
                    dict(id=x.id, label=x.account)
                    for x in advancement.awards(state)
                    if x.phase == "held" and x.handler.entity == str(viewer.user_id)
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        tasks = [
            dict(
                id=x.id,
                revision=state.revision,
                label="Deep-Brain-Spikes acquired",
                phase="held",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ]
        for value in rules.memories(state):
            if viewer.user_id in value.participants or any(
                entry.actor.entity == str(viewer.user_id) for entry in value.contributions
            ):
                tasks.append(
                    dict(
                        id=value.id,
                        revision=state.revision,
                        label="Played memory — " + value.phase,
                        phase=value.phase,
                        pending=False,
                    )
                )
        return tasks
