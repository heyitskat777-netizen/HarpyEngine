"""Mandatory actual-Harpy Defeat, source-owned setup and honest owned consequences."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_defeat as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, tier
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_battle_state import Required as DamageRequired
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_harpy_defeat_state import HarpySetup, NativeHarpyFacts, NativeHarpyRuntime
from girlframe.engine.m3_policy import RULESET
from girlframe.engine.m3_void_state import HarpyState
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.engine.m3_harpy_defeat_state import Declaration, Travel
    from girlframe.services.m2_game import GameService


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def ended_director_judge(
    game: "GameService",
    c: Connection,
    state: GameState,
    original: SceneCast,
    current: SceneCast,
    judge: ActorRef,
    controller: int,
) -> bool:
    """Proof for an already-owned procedural question, never new body/effect authority."""
    from girlframe.engine.m3_handler_consequences import same_handler_body
    from girlframe.engine.m3_world_state import Npc

    if (
        judge.kind != "npc"
        or original.adjudicator != judge
        or not any(x.actor == judge and x.controller == controller for x in original.roles)
    ):
        return False
    npc = next((x for x in state.world.npcs if x.id == judge.entity), None) if state.world else None
    if npc is None or npc.alive or npc.controller != controller or "director" not in npc.jobs:
        return False
    for fact in state.facts:
        if (
            fact.get("kind") != "director_body_ended"
            or fact.get("actor") != judge.model_dump_json()
        ):
            continue
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == fact.get("event"),
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        if source is None or fact not in source.facts or not fact.get("body"):
            continue
        previous_body = Npc.model_validate_json(fact["body"])
        if (
            previous_body.id != judge.entity
            or previous_body.controller != controller
            or not previous_body.alive
            or "director" not in previous_body.jobs
        ):
            continue
        roles = tuple(x for x in original.roles if x.actor != judge)
        revision = original.revision + 1
        for context in source.director_contexts:
            if (
                context.termination_reason != "director_death"
                or context.termination_event != fact["event"]
            ):
                continue
            old = ActorRef(kind="handler", entity=str(context.handler), incarnation=context.id)
            actual = active_handler(source)
            if (
                actual is not None
                and same_handler_body(source, old)
                and any(x.actor == old for x in roles)
            ):
                roles = tuple(
                    {
                        x.actor: x
                        for x in (
                            x.model_copy(update={"actor": actual}) if x.actor == old else x
                            for x in roles
                        )
                    }.values()
                )
                revision += 1
        predicted = original.model_copy(
            update=dict(roles=roles, revision=revision, adjudicator=None)
        )
        if fingerprint(predicted) == fingerprint(current):
            return True
    return False


def ended_actor_source(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> str | None:
    """Prove the exact original's ending without reading a successor through its human UID."""
    from girlframe.engine.m3_handler_consequences import body_original

    candidates = []
    if actor.kind == "pilot":
        candidates = [x.source_event for x in state.career_archives if x.actor == actor]
    elif actor.kind == "handler":
        try:
            original_body = body_original(state, actor)
        except ValueError:
            original_body = None
        candidates = [x.source_event for x in state.handler_archives if x.body == original_body]
    else:
        candidates = [
            str(x["event"])
            for x in state.facts
            if x.get("kind") in ("battle_actor_cast_ended", "director_body_ended")
            and x.get("actor") == actor.model_dump_json()
            and x.get("event")
        ]
        if actor.kind == "external_pilot":
            try:
                condition = rules.harpy(state, actor).condition_event
                if condition:
                    candidates.append(condition)
            except ValueError:
                pass
    for event in reversed(candidates):
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == event,
            )
        )
        if raw is None:
            continue
        proof = GameState.model_validate_json(raw)
        if actor.kind == "pilot" and any(
            x.actor == actor and x.source_event == event for x in proof.career_archives
        ):
            return event
        if actor.kind == "handler":
            try:
                proved_body = body_original(proof, actor)
            except ValueError:
                proved_body = None
            if any(
                x.body == proved_body and x.source_event == event for x in proof.handler_archives
            ):
                return event
        try:
            view = resolve(
                proof,
                actor,
                profiles(c, game.store.campaign_id),
                require_alive=False,
                require_current_profile=False,
            )
        except ValueError:
            continue
        if not view.alive:
            if actor.kind == "npc" and any(
                x.get("kind") == "director_body_ended"
                and x.get("actor") == actor.model_dump_json()
                and x.get("event") == event
                for x in state.facts
            ):
                from girlframe.engine.m3_world_state import Npc

                facts = [
                    x
                    for x in state.facts
                    if x.get("kind") == "director_body_ended"
                    and x.get("actor") == actor.model_dump_json()
                    and x.get("event") == event
                ]
                valid = False
                for fact in facts:
                    if fact not in proof.facts or not fact.get("body"):
                        continue
                    previous = Npc.model_validate_json(fact["body"])
                    current = resolve(
                        state,
                        actor,
                        profiles(c, game.store.campaign_id),
                        require_alive=False,
                        require_current_profile=False,
                    )
                    if (
                        previous.id == actor.entity
                        and previous.alive
                        and "director" in previous.jobs
                        and previous.controller == view.controller == current.controller
                        and not current.alive
                    ):
                        valid = True
                if not valid:
                    continue
            return event
    return None


def restore_death_tags(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    event: str,
) -> GameState:
    """Immutable actual death-choice proof precedes original-return materialization."""
    for effect in state.harpy_defeats:
        if not (
            effect.archived_tag and effect.killer == actor and effect.tag_applied_event is None
        ):
            continue
        source = effect.response_event
        raw = (
            c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == source,
                )
            )
            if source
            else None
        )
        proof = GameState.model_validate_json(raw) if raw else None
        declared = HarpyDefeatService(game.store, game=game)._declaration(
            c, game.action(c, effect.action)
        )
        if (
            proof is None
            or effect not in proof.harpy_defeats
            or effect.phase != "complete"
            or effect.choice != "death"
            or effect.actor != declared.actor
            or effect.work != declared.work
            or effect.source_cast != declared.cast
            or effect.tag_recipient != actor
        ):
            raise WorkflowError("Recover the immutable original Harpy death-Tag consequence.")
    return rules.apply_returned_death_tags(state, actor, event)


def owned_director_procedure(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> ActorView | None:
    """Only this frozen original episode's procedural humans survive its Director's death."""
    meta = action["data"].get("actor_basic")
    frozen = action["data"].get("tag_context")
    if (
        not meta
        or not frozen
        or action["state"] == "complete"
        or action["data"].get("play") not in ("dive_deep", "go_off_duty")
        or not meta.get("adjudicator")
    ):
        return None
    ref = ActorRef.model_validate(meta["ref"])
    judge = ActorRef.model_validate(meta["adjudicator"])
    if ref.kind != "external_pilot" or judge.kind != "npc":
        return None
    original = SceneCast.model_validate_json(json.dumps(frozen["cast"]))
    current = next((x for x in state.scene_casts if x.id == original.id and x.open), None)
    if (
        current is None
        or fingerprint(original) != frozen["cast_sha256"]
        or original.revision != meta["cast_revision"]
        or original.id != action["scene_id"]
        or not ended_director_judge(
            game, c, state, original, current, judge, meta["adjudicator_controller"]
        )
    ):
        return None
    allowed = {
        "tag_window",
        "actor_tag_selection",
        "actor_tag_agreement",
        "tag_resolution",
        "dive_select",
        "dive_effect",
        "dive_table_answer",
        "dive_table_agreement",
        "dive_void_threshold",
        "manual_adjudication",
        "harpy_off_duty_hide",
        "harpy_off_duty_route",
    }
    pending = game.pending(c, action["id"])
    if not pending:
        # Game.respond authenticates the human before marking this exact SQL row answered;
        # apply() then revalidates before the new response event/action is committed.
        saved = game.action(c, action["id"])
        source = action["data"].get("response_event")
        if not source or source == saved["data"].get("response_event"):
            return None
        choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
        pending = [
            dict(x)
            for x in c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.action_id == action["id"],
                    choices.c.state == "answered",
                    ~sa.exists(
                        sa.select(responses.c.choice_id).where(
                            responses.c.campaign_id == choices.c.campaign_id,
                            responses.c.choice_id == choices.c.id,
                        )
                    ),
                )
            ).mappings()
            if (x["kind"] + ":" + x["actor_id"]) in action["data"]["choices"]
        ]
    if not pending or any(x["kind"] not in allowed for x in pending):
        return None
    raw_receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if raw_receipt is not None:
        if json.loads(raw_receipt) != action["data"].get("receipt"):
            return None
    elif not (
        action["state"] == "awaiting_adjudication"
        and action["data"].get("adjudication")
        and any(x["kind"] == "manual_adjudication" for x in pending)
    ):
        return None
    histories = list(
        c.scalars(
            sa.select(t.m2["m2_state_history"].c.body_json)
            .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind.in_(
                    ("m3.play_confirmed", "m3.actor_play_advanced", "m3.manual_adjudicated")
                ),
                sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            )
        )
    )
    if not histories and action["state"] == "awaiting_adjudication":
        requested = c.scalar(
            sa.select(t.events.c.seq).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m3.manual_adjudication_requested",
                t.events.c.actor_id == action["actor_id"],
                sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            )
        )
        if requested is not None:
            previous = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json)
                .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
                .where(t.events.c.campaign_id == game.store.campaign_id, t.events.c.seq < requested)
                .order_by(t.events.c.seq.desc())
                .limit(1)
            )
            if previous is not None:
                histories.append(previous)
    for raw in histories:
        proof = GameState.model_validate_json(raw)
        if not any(x == original for x in proof.scene_casts):
            continue
        npc = (
            next((x for x in proof.world.npcs if x.id == judge.entity), None)
            if proof.world
            else None
        )
        if npc is None or not npc.alive or npc.controller != meta["adjudicator_controller"]:
            continue
        try:
            before = resolve(
                proof, ref, profiles(c, game.store.campaign_id), require_current_profile=False
            )
            now = resolve(
                state, ref, profiles(c, game.store.campaign_id), require_current_profile=False
            )
        except ValueError:
            continue
        if (
            before.controller == now.controller == int(action["actor_id"])
            and before.girl == now.girl == "harpy"
            and before.vessel_id == now.vessel_id
            and before.frame_instance == now.frame_instance
        ):
            return now
    return None


def source_actor_continuation(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> ActorView | None:
    """Read the same actual body after its source-owned Defeat, never a fresh declaration."""
    meta = action["data"].get("actor_basic")
    combat = action["data"].get("engage") or action["data"].get("battle")
    if meta is None or combat is None or not action["data"].get("receipt"):
        return None
    actor = ActorRef.model_validate(meta["ref"])
    if actor.kind != "external_pilot" or combat.get("actor") != actor.model_dump(mode="json"):
        return None
    current = next((x for x in state.scene_casts if x.id == action["scene_id"] and x.open), None)
    if current is None:
        return None
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if receipt is None or json.loads(receipt) != action["data"]["receipt"]:
        return None
    service = HarpyDefeatService(game.store, game)
    bound = profiles(c, game.store.campaign_id)
    for effect in state.harpy_defeats:
        if effect.actor != actor or actor not in effect.departed or effect.phase != "complete":
            continue
        child = game.action(c, effect.action)
        declared = service._declaration(c, child)
        if (
            child["state"] != "complete"
            or child["parent_id"] != action["id"]
            or declared.source_action != action["id"]
            or declared.actor != actor
            or declared.controller != int(action["actor_id"])
        ):
            continue
        work, body, owner = service._source(c, declared.work, pending=False)
        if (
            owner != actor
            or work["state"] != "resolved"
            or body.get("defeat_action") != child["id"]
            or body.get("source_action") != action["id"]
        ):
            continue
        event = effect.response_event or effect.source_event
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == event,
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        first = (
            next((x for x in source.harpy_defeats if x.id == effect.id), None) if source else None
        )
        if first != effect or source is None:
            continue
        if any(
            not any(
                fact.get("kind") == "battle_actor_cast_ended"
                and fact.get("actor") == ref.model_dump_json()
                and fact.get("event") == event
                for fact in source.facts
            )
            for ref in effect.departed
        ):
            continue
        projected = declared.cast.model_copy(
            update={
                "roles": tuple(x for x in declared.cast.roles if x.actor not in effect.departed),
                "revision": declared.cast.revision
                + sum(any(x.actor == ref for x in declared.cast.roles) for ref in effect.departed),
                "adjudicator": None
                if declared.cast.adjudicator in effect.departed
                else declared.cast.adjudicator,
            }
        )
        if fingerprint(projected) != fingerprint(current):
            continue
        original = SceneCast.model_validate(
            (combat if combat.get("cast") else action["data"]["tag_context"])["cast"]
        )
        if (
            fingerprint(original)
            != (combat if combat.get("cast") else action["data"]["tag_context"])["cast_sha256"]
        ):
            continue
        if original != declared.cast:
            old = original.adjudicator
            human = next((x.controller for x in original.roles if x.actor == old), None)
            if (
                old is None
                or human is None
                or not ended_director_judge(game, c, source, original, declared.cast, old, human)
            ):
                continue
        rows = c.execute(
            sa.select(t.m2["m2_state_history"].c.body_json)
            .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.actor_id == action["actor_id"],
                t.events.c.kind.in_(("m3.actor_play_advanced", "m3.rolled")),
                sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            )
            .order_by(t.events.c.seq)
        ).scalars()
        for saved in rows:
            rolled = GameState.model_validate_json(saved)
            if not any(x == original for x in rolled.scene_casts):
                continue
            original_view = resolve(rolled, actor, bound, require_current_profile=False)
            current_view = resolve(
                state, actor, bound, require_alive=False, require_current_profile=False
            )
            if (
                original_view.controller == current_view.controller == int(action["actor_id"])
                and original_view.vessel_id == current_view.vessel_id
                and original_view.frame_instance == current_view.frame_instance
            ):
                service._runtime(c, state, actor)
                return current_view
    return None


class HarpyDefeatService:
    def __init__(self, store: OnboardingStore, game: "GameService|None" = None):
        from girlframe.services.m2_game import GameService

        self.store, self.game = store, game or GameService(store)

    def _row(self, c: Connection, identity: str, *, first: bool = False) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision if first else table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] != "harpy_defeat":
            raise WorkflowError("Open the actual original Harpy Defeat consequence.")
        return dict(row)

    def _source(
        self, c: Connection, identity: str, *, pending: bool = True
    ) -> tuple[dict[str, Any], dict[str, Any], ActorRef]:
        row, first = self._row(c, identity), self._row(c, identity, first=True)
        body, start = json.loads(row["body_json"]), json.loads(first["body_json"])
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == first["event_id"],
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        fact = (
            next(
                (
                    x
                    for x in source.facts
                    if x.get("kind") == "battle_damage_stage"
                    and x.get("id") == identity
                    and x.get("requirement")
                ),
                None,
            )
            if source
            else None
        )
        required = DamageRequired.model_validate_json(fact["requirement"]) if fact else None
        if (
            required is None
            or fact is None
            or start.get("source_action") != (fact.get("source_action") or None)
            or start.get("source_work") != (fact.get("source_work") or None)
            or start.get("requirement") != required.model_dump(mode="json")
            or required.kind != "harpy_defeat"
            or required.target.kind != "external_pilot"
            or start.get("owner") != required.target.model_dump(mode="json")
            or any(
                body.get(k) != start.get(k)
                for k in (
                    "owner",
                    "character",
                    "source_action",
                    "source_work",
                    "requirement",
                    "continuation",
                )
            )
        ):
            raise WorkflowError(
                "SOURCE_HARPY_DEFEAT_MISSING: recover the actual immutable defeated body/source."
            )
        actor = required.target
        assert source is not None
        original = next((x for x in source.harpy_states if x.id == actor.entity), None)
        world = (
            next(
                (x for x in source.world.pilots if x.id == actor.entity and x.kind == "harpy"), None
            )
            if source.world
            else None
        )
        controller = original.controller if original else world.controller if world else None
        if (
            controller is None
            or str(controller) != first["owner_id"]
            or first["subject_id"] != str(controller)
        ):
            raise WorkflowError("Recover the actual original Harpy's controlling human.")
        if pending and row["state"] == "resolved":
            raise WorkflowError("This actual original Harpy Defeat is already resolved.")
        return row, body, actor

    def _runtime(
        self, c: Connection, state: GameState, actor: ActorRef
    ) -> HarpyState | NativeHarpyRuntime:
        body = rules.harpy(state, actor)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == body.source_event,
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        if isinstance(body, HarpyState):
            original = (
                next((x for x in proof.harpy_states if x.id == body.id), None) if proof else None
            )
            if original is None or any(
                getattr(original, k) != getattr(body, k)
                for k in (
                    "origin",
                    "controller",
                    "source_event",
                    "original_archive",
                    "body_vessel",
                    "frame_instance",
                )
            ):
                raise WorkflowError("Recover the actual original Harpy's birth/body source.")
        else:
            native_source = (
                next((x for x in proof.native_harpies if x.id == body.id), None) if proof else None
            )
            setup = (
                next(
                    (
                        x
                        for x in proof.harpy_setups
                        if x.response_event == body.source_event and x.facts.actor == actor
                    ),
                    None,
                )
                if proof
                else None
            )
            event = c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == body.source_event,
                )
            ).first()
            if (
                native_source is None
                or setup is None
                or setup.state != "approved"
                or event != ("m3.harpy_runtime_approved", str(setup.handler))
                or any(
                    getattr(native_source, k) != getattr(body, k)
                    for k in (
                        "controller",
                        "source_event",
                        "proposed_event",
                        "body_vessel",
                        "frame_instance",
                    )
                )
                or state.world is None
                or any(x.tags for x in state.world.pilots if x.id == body.id)
            ):
                raise WorkflowError(
                    "Recover the actual native Harpy's factual setup and sole Tag authority."
                )
        return body

    def setup_preview(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row, _, actor = self._source(c, identity)
            if str(viewer.user_id) != row["owner_id"]:
                raise WorkflowError(
                    "Only the actual Harpy's human records its current factual runtime."
                )
            state = load_state(c, self.store.campaign_id)
            world = (
                next(
                    (x for x in state.world.pilots if x.id == actor.entity and x.kind == "harpy"),
                    None,
                )
                if state.world
                else None
            )
            if (
                world is None
                or any(x.id == actor.entity for x in state.harpy_states)
                or any(x.id == actor.entity for x in state.native_harpies)
            ):
                raise WorkflowError(
                    "This actual body already has its source-owned resources or is not a "
                    "native Harpy."
                )
            return dict(
                work=identity,
                actor=actor.model_dump(mode="json"),
                game_revision=state.revision,
                name=world.name,
                source_sha256=fingerprint(world),
                frame_cell=world.cell,
                tags=[x.model_dump(mode="json") for x in world.tags],
            )

    def setup_preview_actor(self, viewer: GuildViewer, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            world = (
                next(
                    (
                        x
                        for x in state.world.pilots
                        if x.id == actor.entity and x.kind == "harpy" and x.alive
                    ),
                    None,
                )
                if state.world
                else None
            )
            if (
                actor.kind != "external_pilot"
                or world is None
                or world.controller != viewer.user_id
                or any(x.id == actor.entity for x in state.native_harpies)
            ):
                raise WorkflowError(
                    "Choose your actual living native World Harpy without an existing runtime."
                )
            return dict(
                work=None,
                actor=actor.model_dump(mode="json"),
                game_revision=state.revision,
                name=world.name,
                source_sha256=fingerprint(world),
                frame_cell=world.cell,
                tags=[x.model_dump(mode="json") for x in world.tags],
                custody=world.custody,
                custodian=world.custodian,
                actors=self._setup_actors(c, state, viewer),
            )

    def _setup_actors(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> list[dict[str, Any]]:
        refs = [
            ActorRef(kind="pilot", entity=uid, incarnation=x.character_id)
            for uid, x in state.sheets.items()
            if x.character_id
        ]
        refs.extend(x.actor for x in state.career_archives)
        body = active_handler(state)
        if body is not None:
            refs.append(body)
        refs.extend(x.actor for x in state.handler_archives)
        if state.world:
            refs.extend(
                ActorRef(kind="npc", entity=x.id)
                for x in state.world.npcs
                if x.revealed or x.controller == viewer.user_id
            )
            refs.extend(
                ActorRef(kind="external_pilot", entity=x.id)
                for x in state.world.pilots
                if x.revealed or x.controller == viewer.user_id
            )
        if state.world:
            refs.extend(
                ActorRef(kind="gorgon", entity=x.id)
                for x in state.world.gorgons
                if x.revealed or viewer.user_id == state.handler
            )
        result = []
        for ref in dict.fromkeys(refs):
            if ref.kind == "pilot" and (
                ref.entity not in state.sheets
                or state.sheets[ref.entity].character_id != ref.incarnation
            ):
                from girlframe.engine.m3_careers import original_sheet

                label = original_sheet(state, ref).callsign
            elif ref.kind == "handler" and body != ref:
                label = "Original archived Handler"
            else:
                try:
                    label = resolve(
                        state,
                        ref,
                        profiles(c, self.store.campaign_id),
                        require_alive=False,
                        require_current_profile=False,
                    ).label
                except ValueError:
                    continue
            result.append(
                dict(
                    ref=ref.model_dump(mode="json"),
                    token=ref.token,
                    label=label,
                    controller=int(ref.entity)
                    if ref.kind in ("pilot", "handler")
                    else resolve(
                        state,
                        ref,
                        profiles(c, self.store.campaign_id),
                        require_alive=False,
                        require_current_profile=False,
                    ).controller,
                )
            )
        return result

    def propose_runtime(
        self, viewer: GuildViewer, key: str, expected: int, facts: NativeHarpyFacts
    ) -> dict[str, Any]:
        return self.propose_setup(viewer, key, None, expected, facts)

    def propose_setup(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str | None,
        expected: int,
        facts: NativeHarpyFacts,
    ) -> dict[str, Any]:
        facts = NativeHarpyFacts.model_validate_json(facts.model_dump_json())

        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if identity is not None:
                row, _, actor = self._source(c, identity)
                source_owner = int(row["owner_id"])
            else:
                actor = facts.actor
                source_owner = viewer.user_id
            world = (
                next((x for x in state.world.pilots if x.id == actor.entity), None)
                if state.world
                else None
            )
            if (
                state.revision != expected
                or viewer.user_id != source_owner
                or facts.actor != actor
                or world is None
                or world.controller != viewer.user_id
                or world.kind != "harpy"
                or not world.alive
                or facts.frame_cell != world.cell
                or (
                    any(x.id == actor.entity for x in state.harpy_states)
                    or any(x.id == actor.entity for x in state.native_harpies)
                )
                or any(x.facts.actor == actor and x.state == "proposed" for x in state.harpy_setups)
            ):
                raise WorkflowError(
                    "Refresh the actual untouched World Harpy and its factual setup."
                )
            if facts.custody != ("core" if world.custody == "converted" else world.custody):
                raise WorkflowError(
                    "Preserve the actual existing World custody source during factual setup."
                )
            if facts.custodian is not None:
                custodian = resolve(
                    state,
                    facts.custodian,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if world.custodian != custodian.controller:
                    raise WorkflowError(
                        "The real custodian's controller must match the actual World custody "
                        "record."
                    )
            if {(x.id, x.label) for x in facts.tags} != {(x.id, x.label) for x in world.tags}:
                raise WorkflowError(
                    "Adopt every actual existing World Tag without adding, removing or "
                    "renaming one."
                )
            for tag in facts.tags:
                old_tag = next(x for x in world.tags if x.id == tag.id)
                if tag.giver_ref is not None and old_tag.giver_entity not in (
                    tag.giver_ref.token,
                    tag.giver_ref.kind + ":" + tag.giver_ref.entity
                    if tag.giver_ref.incarnation is None
                    else "",
                    "handler:" + tag.giver_ref.incarnation
                    if tag.giver_ref.kind == "handler" and tag.giver_ref.incarnation
                    else "",
                ):
                    raise WorkflowError(
                        "Preserve the source Tag's actual setter, not a current human alias."
                    )
                if (
                    tag.giver_ref is None
                    or tag.gm_setter_appointment is not None
                    or tag.gm_setter_event is not None
                ):
                    raise WorkflowError(
                        "Record the actual existing Tag setter role, without inventing a new GM "
                        "Tag event."
                    )
                if tag.giver_ref.kind == "pilot":
                    from girlframe.engine.m3_careers import original_sheet

                    original_sheet(state, tag.giver_ref)
                    controller = int(tag.giver_ref.entity)
                elif tag.giver_ref.kind == "handler":
                    from girlframe.engine.m3_handler_consequences import body_original

                    body_original(state, tag.giver_ref)
                    controller = int(tag.giver_ref.entity)
                else:
                    controller = resolve(
                        state,
                        tag.giver_ref,
                        profiles(c, self.store.campaign_id),
                        require_alive=False,
                        require_current_profile=False,
                    ).controller
                if tag.giver != controller:
                    raise WorkflowError("The factual Tag setter cannot alias another human.")
            handler, appointment = MedicalService(self.store)._handler(c)
            event, proposal = str(uuid4()), str(uuid4())
            state.harpy_setups.append(
                HarpySetup(
                    id=proposal,
                    owner=viewer.user_id,
                    handler=handler,
                    appointment=appointment,
                    source_event=event,
                    source_sha256=fingerprint(world),
                    facts=facts,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_runtime_proposed",
                state,
                event_id=event,
                setup=proposal,
            )
            return dict(id=proposal, state="proposed")

        return self.store._write(
            viewer,
            key,
            "m3.harpy_runtime_proposed",
            dict(work=identity, expected=expected, facts=facts.model_dump(mode="json")),
            operation,
            auto_audit=False,
            authorize=access,
        )

    def review_setup(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        approve: bool,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            HandlerService(self.store).authorize(c, viewer)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            setup = next((x for x in state.harpy_setups if x.id == identity), None)
            if (
                setup is None
                or setup.state != "proposed"
                or state.revision != expected
                or not account.strip()
                or MedicalService(self.store)._handler(c) != (setup.handler, setup.appointment)
            ):
                raise WorkflowError(
                    "Reopen the actual source-owned setup and current GM factual review."
                )
            world = (
                next((x for x in state.world.pilots if x.id == setup.facts.actor.entity), None)
                if state.world
                else None
            )
            if approve and (world is None or fingerprint(world) != setup.source_sha256):
                raise WorkflowError(
                    "The actual existing World Harpy changed; its resources were preserved."
                )
            event = str(uuid4())
            state.harpy_setups = [
                x.model_copy(
                    update=dict(
                        state="approved" if approve else "declined",
                        response_event=event,
                        review=account,
                    )
                )
                if x.id == identity
                else x
                for x in state.harpy_setups
            ]
            if approve:
                assert world is not None
                facts = setup.facts
                state.native_harpies.append(
                    NativeHarpyRuntime(
                        id=world.id,
                        controller=world.controller,
                        source_event=event,
                        proposed_event=setup.source_event,
                        world_source_sha256=setup.source_sha256,
                        body_vessel="native-harpy-body:" + identity,
                        frame_instance="initial:" + world.id,
                        cell=facts.girl_cell,
                        frame_cell=facts.frame_cell,
                        linked=facts.linked,
                        heat=facts.heat,
                        identities=facts.identities,
                        tags=facts.tags,
                        frame_shutdown=facts.frame_shutdown,
                        body_incapacitated=facts.body_incapacitated,
                        condition_event=event,
                        custody=facts.custody,
                        custodian=facts.custodian,
                        custody_event=world.custody_event if facts.custody != "free" else None,
                    )
                )
                assert state.world is not None
                state.world = state.world.model_copy(
                    update={
                        "pilots": tuple(
                            x.model_copy(update={"tags": ()}) if x.id == world.id else x
                            for x in state.world.pilots
                        )
                    }
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_runtime_approved" if approve else "m3.harpy_runtime_declined",
                state,
                event_id=event,
                setup=identity,
            )
            return dict(id=identity, state="approved" if approve else "declined")

        return self.store._write(
            viewer,
            key,
            "m3.harpy_runtime_reviewed",
            dict(id=identity, expected=expected, approve=approve, account=account),
            operation,
            auto_audit=False,
            authorize=access,
        )

    def _declaration(self, c: Connection, action: dict[str, Any]) -> "Declaration":
        from girlframe.engine.m3_harpy_defeat_state import Declaration

        meta = action["data"]["harpy_defeat"]
        fields = Declaration.model_fields
        declared = Declaration.model_validate_json(json.dumps({k: meta[k] for k in fields}))
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == declared.source_event,
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        original = (
            next((x for x in source.harpy_defeat_declarations if x.id == action["id"]), None)
            if source
            else None
        )
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == declared.source_event,
            )
        ).first()
        if original != declared or event != ("m3.harpy_defeat_confirmed", str(declared.controller)):
            raise WorkflowError(
                "Recover the actual original Harpy Defeat declaration and controlling human."
            )
        return declared

    def authorize(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any], *, read: bool = False
    ) -> "Declaration":
        self.game.authorize(c, viewer, game=False)
        if not read:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
        declared = self._declaration(c, action)
        if viewer.user_id not in action["data"]["participants"]:
            raise WorkflowError("Only an original table participant may use this Harpy Defeat.")
        approval = self.store.policy.m3_approval
        if not read and (approval is None or approval.registry_sha256 != declared.registry):
            raise WorkflowError(
                "M3_POLICY_CHANGED: recover the actual original Harpy Defeat approval."
            )
        if not read and MedicalService(self.store)._handler(c)[1] != declared.appointment:
            raise WorkflowError("Recover the actual source-appointed human GM before continuing.")
        return declared

    def begin(
        self, viewer: GuildViewer, key: str, identity: str, *, channel: int | None = None
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)

        def operation(c: Connection) -> dict[str, Any]:
            source_channel = channel
            from girlframe.engine.m3_harpy_defeat_state import Declaration

            self.game.unpaused(c)
            row, source, actor = self._source(c, identity)
            from girlframe.services.m3_battle import damage_prerequisites

            damage_prerequisites(self.game, c, row)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("Only the original Harpy's actual human may begin this Defeat.")
            state = load_state(c, self.store.campaign_id)
            body = self._runtime(c, state, actor)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actual.controller != viewer.user_id:
                raise WorkflowError("The actual original Harpy changed controller.")
            actions = t.m2["m2_actions"]
            previous = c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    sa.func.json_extract(actions.c.body_json, "$.harpy_defeat.work") == identity,
                )
            )
            if previous:
                raise WorkflowError(
                    "This source already has its saved Harpy Defeat; resume that exact action."
                )
            parent = (
                self.game.action(c, source["source_action"])
                if source.get("source_action")
                else None
            )
            if parent:
                requests = [
                    x
                    for x in self.game.pending(c, parent["id"])
                    if x["id"] == source.get("continuation")
                    and x["kind"] == "battle_harpy_defeat"
                    and json.loads(x["body_json"]).get("work_id") == identity
                ]
                if len(requests) != 1:
                    raise WorkflowError("Recover the actual held source Harpy Defeat continuation.")
                source_channel = int(parent["channel_id"])
                active = c.scalar(
                    sa.select(actions.c.id)
                    .where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.parent_id == parent["id"],
                        actions.c.state.not_in(("complete", "aborted")),
                    )
                    .limit(1)
                )
                if active:
                    raise WorkflowError("Finish the actual pending source response Play first.")
            else:
                if self.game.pending_actions(c):
                    raise WorkflowError("Finish the pending scene Play first.")
                if source_channel is None:
                    candidates = [
                        x
                        for x in state.scene_casts
                        if x.open
                        and any(
                            r.actor == actor and r.controller == viewer.user_id for r in x.roles
                        )
                    ]
                    if len(candidates) != 1:
                        raise WorkflowError("Choose the actual open scene containing this Harpy.")
                    source_channel = candidates[0].channel
            assert source_channel is not None
            scene = self.game.scene(c, source_channel)
            cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
            if cast is None or not any(
                x.actor == actor and x.controller == viewer.user_id for x in cast.roles
            ):
                raise WorkflowError("Join the actual Harpy role in this source scene first.")
            campaign_gm, appointment = MedicalService(self.store)._handler(c)
            from girlframe.services.m3_actor_plays import ActorPlayService

            judge = ActorPlayService(self.game)._judge(c, state, cast, actor)
            gm = judge.controller
            if cast.facilitator != campaign_gm:
                raise WorkflowError(
                    "The actual source GM must be the scene's explicit facilitator."
                )
            for role in cast.roles:
                if (
                    resolve(
                        state,
                        role.actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    ).controller
                    != role.controller
                ):
                    raise WorkflowError("Recover the actual original scene roles before Defeat.")
            lock = self.game.lock(c, source_channel)
            if parent:
                root = parent
                while root["parent_id"]:
                    root = self.game.action(c, root["parent_id"])
                if not lock or lock["state"] != "held" or lock["action_id"] != root["id"]:
                    raise WorkflowError(
                        "The actual original source must hold its acknowledged chat lock."
                    )
            elif lock and lock["state"] != "released":
                raise WorkflowError("Restore the previous scene chat lock first.")
            amount, girl = rules.modifier(state, actor, cast)
            event, action_id = str(uuid4()), str(uuid4())
            approval = self.store.policy.m3_approval
            assert approval is not None
            handler_body = active_handler(state)
            declared = Declaration.model_validate_json(
                json.dumps(
                    dict(
                        id=action_id,
                        work=identity,
                        work_revision=row["revision"],
                        actor=actor.model_dump(mode="json"),
                        controller=viewer.user_id,
                        frame_instance=body.frame_instance,
                        source_event=event,
                        source_sha256=actual.source_sha256,
                        source_action=parent["id"] if parent else None,
                        source_request=source.get("continuation"),
                        registry=approval.registry_sha256,
                        gm_controller=gm,
                        adjudicator=judge.ref.model_dump(mode="json") if judge.ref else None,
                        appointment=appointment,
                        handler=handler_body.model_dump(mode="json")
                        if handler_body is not None
                        else None,
                        cast=cast.model_dump(mode="json"),
                        modifier=amount,
                        bond_girl=girl.model_dump(mode="json") if girl else None,
                    )
                )
            )
            meta = declared.model_dump(mode="json")
            data = dict(
                harpy_defeat=meta,
                play="harpy_defeat",
                participants=sorted({x.controller for x in cast.roles} | {gm}),
                handler=gm,
                receipt=None,
                modifiers=[],
                result={},
                choices={},
                prepared=dict(play="harpy_defeat", heat=0),
                tag_context=dict(
                    actor=actor.model_dump(mode="json"),
                    cast=cast.model_dump(mode="json"),
                    cast_sha256=fingerprint(cast),
                    handler=meta["handler"],
                ),
                m3_shared=dict(registry=declared.registry),
            )
            prohibition = next(
                (x for x in body.blocked_plays if x.play in ("defeat", "harpy_defeat")), None
            )
            if prohibition:
                from girlframe.engine.m3_adjudication_state import Required

                data["adjudication"] = Required(
                    play="harpy_defeat",
                    actor=actor,
                    actor_controller=viewer.user_id,
                    handler=active_handler(state) if judge.ref is None else None,
                    adjudicator=judge.ref,
                    gm_controller=gm,
                    appointment=appointment,
                    prohibition=prohibition,
                    source_kind="harpy_defeat_work",
                    source_id=identity,
                    source_revision=row["revision"],
                    registry=declared.registry,
                ).model_dump(mode="json")
            c.execute(
                actions.insert().values(
                    campaign_id=self.store.campaign_id,
                    id=action_id,
                    actor_id=str(viewer.user_id),
                    channel_id=str(source_channel),
                    scene_id=scene["id"],
                    parent_id=parent["id"] if parent else None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data, sort_keys=True),
                )
            )
            if parent is None:
                locks = t.m2["m2_locks"]
                values = dict(
                    action_id=action_id,
                    state="acquiring",
                    body_json="{}",
                    lease_until=0,
                    claim_token=None,
                )
                if lock:
                    c.execute(
                        locks.update()
                        .where(
                            locks.c.campaign_id == self.store.campaign_id,
                            locks.c.channel_id == str(source_channel),
                        )
                        .values(**values)
                    )
                else:
                    c.execute(
                        locks.insert().values(
                            campaign_id=self.store.campaign_id,
                            channel_id=str(source_channel),
                            **values,
                        )
                    )
            state.harpy_defeat_declarations.append(declared)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_defeat_confirmed",
                state,
                event_id=event,
                action_id=action_id,
                work_id=identity,
            )
            return dict(action_id=action_id, state="acquiring")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_defeat_confirmed",
                dict(work=identity, channel=channel),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _current(
        self, c: Connection, action: dict[str, Any], *, unrolled: bool = False
    ) -> tuple[GameState, HarpyState | NativeHarpyRuntime, "Declaration"]:
        declared = self._declaration(c, action)
        state = load_state(c, self.store.campaign_id)
        body = self._runtime(c, state, declared.actor)
        if body.controller != declared.controller or body.frame_instance != declared.frame_instance:
            raise WorkflowError("Recover the exact original Harpy body and Frame instance.")
        if action["state"] != "complete":
            work_row, _, _ = self._source(c, declared.work)
            if unrolled:
                from girlframe.services.m3_battle import damage_prerequisites

                damage_prerequisites(self.game, c, work_row)
        cast = next((x for x in state.scene_casts if x.id == declared.cast.id and x.open), None)
        if cast is None:
            raise WorkflowError("Recover the original actual Harpy scene before continuing.")
        from girlframe.services.m3_void_keep import _ended_handler_cast

        procedural_ended = declared.adjudicator is not None and ended_director_judge(
            self.game,
            c,
            state,
            declared.cast,
            cast,
            declared.adjudicator,
            declared.gm_controller,
        )
        departures = set()
        for fact in state.facts:
            if fact.get("kind") != "battle_actor_cast_ended" or not fact.get("actor"):
                continue
            ref = ActorRef.model_validate_json(fact["actor"])
            if not any(x.actor == ref for x in declared.cast.roles):
                continue
            saved = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == fact.get("event"),
                )
            )
            source_state = GameState.model_validate_json(saved) if saved else None
            if source_state is not None and fact in source_state.facts:
                departures.add(ref)
        if (
            cast != declared.cast
            and not procedural_ended
            and not _ended_handler_cast(state, declared.cast, cast, state.handler or 0)
        ):
            expected = tuple(x for x in declared.cast.roles if x.actor not in departures)
            if (
                not departures
                or cast.roles != expected
                or cast.facilitator != declared.cast.facilitator
                or cast.channel != declared.cast.channel
                or cast.adjudicator
                != (None if declared.cast.adjudicator in departures else declared.cast.adjudicator)
            ):
                raise WorkflowError(
                    "The actual source cast changed; recover the saved outcome without rerolling."
                )
        # This is a derived current projection of proved removals, never rewritten source history.
        action["data"]["tag_context"].update(
            cast=cast.model_dump(mode="json"), cast_sha256=fingerprint(cast)
        )
        from girlframe.services.m3_actor_plays import ActorPlayService

        if not procedural_ended:
            judge = ActorPlayService(self.game)._judge(c, state, cast, declared.actor)
            if judge.ref != declared.adjudicator or judge.controller != declared.gm_controller:
                raise WorkflowError("Recover this actual source's original rules adjudicator.")
        if unrolled:
            actual = resolve(
                state,
                declared.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            amount, girl = rules.modifier(state, declared.actor, cast)
            if (
                actual.source_sha256 != declared.source_sha256
                or amount != declared.modifier
                or girl != declared.bond_girl
            ):
                raise WorkflowError(
                    "The actual unrolled Harpy resources or scene Bond changed; no RNG was "
                    "consumed."
                )
        return state, body, declared

    def roll(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        def access(c: Connection) -> None:
            action = self.game.action(c, identity)
            declared = self.authorize(c, viewer, action)
            if viewer.user_id != declared.controller:
                raise WorkflowError("Only the original Harpy's human resumes its mandatory roll.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            action = self.game.action(c, identity)
            if action["data"].get("receipt"):
                return dict(action_id=identity, receipt=action["data"]["receipt"])
            if action["state"] not in ("acquiring", "ready_to_roll"):
                raise WorkflowError("Resume the actual saved Harpy Defeat state.")
            lock = self.game.lock(c, action["channel_id"])
            root = action
            while root["parent_id"]:
                root = self.game.action(c, root["parent_id"])
            if lock is None or lock["state"] != "held" or lock["action_id"] != root["id"]:
                raise WorkflowError("LOCK_NOT_ACKNOWLEDGED: no Harpy Defeat RNG was consumed.")
            state, body, declared = self._current(c, action, unrolled=True)
            if action["data"].get("adjudication"):
                from girlframe.services.m3_adjudication import reserve_request

                return reserve_request(self.game, c, viewer, action, key=key)
            faces = self.game.dice.roll()
            if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                raise WorkflowError("The dice source returned invalid faces.")
            event = str(uuid4())
            receipt = dict(
                id=str(uuid4()),
                action_id=identity,
                faces=list(faces),
                heat=0,
                pre_total=sum(faces) + declared.modifier,
                base_modifier=declared.modifier,
                modifier_source="Intense Bond with a Girl in this scene"
                if declared.bond_girl
                else "Harpy Defeat",
                pre_modifiers=[],
                rng_source=self.game.rng_source,
                rolled_utc=datetime.now(UTC).isoformat(),
                ruleset=RULESET,
            )
            self._save_receipt(c, viewer, key, action, state, receipt, event)
            return dict(action_id=identity, receipt=receipt)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_defeat_rolled",
                dict(action_id=identity),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _save_receipt(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        action: dict[str, Any],
        state: GameState,
        receipt: dict[str, Any],
        event: str,
    ) -> None:
        declared = self._declaration(c, action)
        c.execute(
            t.m2["m2_receipts"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                action_id=action["id"],
                id=receipt["id"],
                body_json=json.dumps(receipt, sort_keys=True),
            )
        )
        action["data"]["receipt"] = receipt
        action["data"]["harpy_defeat"]["roll_event"] = event
        self.game.save_action(c, action, state="tag_window")
        for human in action["data"]["participants"]:
            self.game.request(c, action, human, "tag_window")
        label = resolve(
            state,
            declared.actor,
            profiles(c, self.store.campaign_id),
            require_current_profile=False,
        ).label
        self.game.queue(
            c, action, "receipt", dict(receipt=receipt, callsign=label, play="harpy_defeat")
        )
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.harpy_defeat_rolled" if receipt.get("faces") else "m3.manual_adjudicated",
            state,
            event_id=event,
            action_id=action["id"],
            receipt_id=receipt["id"],
        )

    def manual_receipt(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        action: dict[str, Any],
        total: int,
        reason: str,
        request_id: str,
    ) -> dict[str, Any]:
        from girlframe.engine import m3_adjudication
        from girlframe.engine.m3_adjudication_state import Decision, Required
        from girlframe.services.m3_adjudication import verify

        required = Required.model_validate_json(json.dumps(action["data"]["adjudication"]))
        state, _, declared = self._current(c, action, unrolled=True)
        verify(self.game, c, state, required)
        self.authorize(c, viewer, action)
        self.game.unpaused(c)
        request = next(
            (
                x
                for x in self.game.pending(c, action["id"])
                if x["id"] == request_id
                and x["kind"] == "manual_adjudication"
                and x["actor_id"] == str(required.controller)
            ),
            None,
        )
        lock = self.game.lock(c, action["channel_id"])
        if (
            required.controller != viewer.user_id
            or request is None
            or action["state"] != "awaiting_adjudication"
            or action["data"].get("receipt")
            or lock is None
            or lock["state"] != "held"
        ):
            raise WorkflowError(
                "Use the actual source-appointed human GM's pending Harpy adjudication."
            )
        event = str(uuid4())
        decision = Decision(
            id=str(uuid4()),
            action=action["id"],
            request=request_id,
            required=required,
            total=total,
            reason=reason.strip(),
            source_event=event,
        )
        receipt = m3_adjudication.receipt(decision, str(uuid4()), datetime.now(UTC).isoformat())
        receipt["ruleset"] = RULESET
        choices = t.m2["m2_choices"]
        c.execute(
            choices.update()
            .where(choices.c.campaign_id == self.store.campaign_id, choices.c.id == request_id)
            .values(
                state="resolved",
                revision=request["revision"] + 1,
                body_json=json.dumps(
                    json.loads(request["body_json"])
                    | dict(decision=decision.model_dump(mode="json"))
                ),
            )
        )
        self._save_receipt(c, viewer, key, action, state, receipt, event)
        c.execute(
            t.m2["m2_responses"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                choice_id=request_id,
                actor_id=str(viewer.user_id),
                event_id=event,
                answer_json=json.dumps(dict(manual_adjudication=decision.model_dump(mode="json"))),
            )
        )
        return dict(action_id=action["id"], receipt=receipt)

    def _results(self, c: Connection, action: dict[str, Any]) -> None:
        total = action["data"]["receipt"]["pre_total"] + sum(
            x["amount"] for x in action["data"]["modifiers"]
        )
        action["data"]["result"].update(total=total, tier=tier(total))
        action["state"] = "awaiting_choices"
        self.game.request(c, action, int(action["actor_id"]), "harpy_defeat_select")

    def _close_tags(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        from girlframe.engine import m3_actor_plays as actor_rules
        from girlframe.engine.m2 import higher
        from girlframe.engine.m3_tag_markers import modifier
        from girlframe.services import m3_tag_markers as markers

        declared = self._declaration(c, action)
        proposals = []
        for human in action["data"]["participants"]:
            saved = action["data"]["choices"].get("tag_window:" + str(human))
            if saved and saved["options"] == ["tag"]:
                answer = ChoiceAnswer.model_validate_json(json.dumps(saved))
                try:
                    marker = markers.saved(self.game, c, state, action, human)
                except WorkflowError:
                    markers.reopen(self.game, c, action, human)
                    return
                proposals.append((human, answer, marker))
        selected = None
        candidate = action["data"]["harpy_defeat"].get("tag_candidate")
        if candidate:
            selected = next((x for x in proposals if str(x[0]) == candidate), None)
            if selected is None:
                raise WorkflowError("Recover the actual original discussed Harpy Tag proposal.")
        elif len(proposals) > 1 and any(
            x[2].actor is None or x[2].actor.kind not in ("pilot", "handler") for x in proposals
        ):
            action["data"]["harpy_defeat"]["tag_candidates"] = [str(x[0]) for x in proposals]
            self.game.request(c, action, declared.gm_controller, "harpy_tag_select")
            return
        else:
            for entry in proposals:
                if selected is None:
                    selected = entry
                else:
                    assert entry[2].actor is not None and selected[2].actor is not None
                    if higher(state, int(entry[2].actor.entity), int(selected[2].actor.entity)):
                        selected = entry
        if selected:
            human, answer, marker = selected
            if answer.number not in (-1, 1):
                raise WorkflowError("Choose the actual Tag direction.")
            amount = modifier(state, declared.actor, marker, -1 if answer.number == -1 else 1)
            repeated = actor_rules.mark(state, declared.actor, answer.denied[0], action["scene_id"])
            action["data"]["modifiers"].append(
                dict(
                    source="girl_tag",
                    amount=amount,
                    tag=answer.denied[0],
                    marker=marker.model_dump(mode="json"),
                )
            )
            if repeated:
                self.game.request(
                    c,
                    action,
                    declared.controller,
                    "harpy_tag_resolution",
                    dict(tag=answer.denied[0]),
                )
                return
        self._results(c, action)

    def _apply(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        row: dict[str, Any],
        answer: ChoiceAnswer,
        viewer: GuildViewer,
    ) -> None:
        from girlframe.engine import m3_actor_plays as actor_rules
        from girlframe.services import m3_tag_markers as markers

        declared = self._declaration(c, action)
        kind = row["kind"]
        if kind == "tag_window":
            if answer.options == ("pass",):
                if (
                    answer.denied
                    or answer.fields
                    or answer.number is not None
                    or answer.flag is not None
                    or answer.member
                    or answer.text
                ):
                    raise WorkflowError(
                        "A Harpy Tag pass cannot spend resources or assert another role's choice."
                    )
            elif answer.options == ("tag",) and len(answer.denied) == 1:
                if int(row["actor_id"]) == declared.controller:
                    raise WorkflowError("Only another player may mark this Harpy Tag.")
                if (
                    set(answer.fields) - {"marker"}
                    or answer.flag is not None
                    or answer.member
                    or answer.number not in (-1, 1)
                    or not answer.text.strip()
                ):
                    raise WorkflowError(
                        "Choose an actual marker, one observed Tag, direction and relevance."
                    )
                marker = markers.select(
                    self.game, c, state, action, int(row["actor_id"]), answer.fields.get("marker")
                )
                tag = next(
                    (
                        x
                        for x in rules.harpy(state, declared.actor).tags
                        if x.id == answer.denied[0]
                    ),
                    None,
                )
                if (
                    tag is None
                    or int(row["actor_id"]) not in tag.observers
                    or tag.scene_used == action["scene_id"]
                ):
                    raise WorkflowError("Choose an actually observed, unused Harpy Tag.")
                actor_rules.proposal(
                    state,
                    declared.actor,
                    marker.actor,
                    marker.controller,
                    profiles(c, self.store.campaign_id),
                    tag.id,
                    action["scene_id"],
                    answer.number,
                    answer.text,
                )
                markers.capture(self.game, c, state, action, marker)
            else:
                raise WorkflowError("Pass or propose exactly one actual Harpy Tag.")
            if not any(x["kind"] == "tag_window" for x in self.game.pending(c, action["id"])):
                self._close_tags(c, state, action)
        elif kind == "harpy_tag_select":
            if (
                int(row["actor_id"]) != declared.gm_controller
                or len(answer.options) != 1
                or answer.options[0] not in action["data"]["harpy_defeat"].get("tag_candidates", [])
                or answer.denied
                or answer.fields
                or answer.flag is not None
            ):
                raise WorkflowError(
                    "The actual source GM selects one actual proposal for table discussion."
                )
            meta = action["data"]["harpy_defeat"]
            meta["tag_candidate"] = answer.options[0]
            meta["tag_agreements"] = {str(declared.gm_controller): True}
            for human in action["data"]["participants"]:
                if human != declared.gm_controller:
                    self.game.request(c, action, human, "harpy_tag_agreement")
            if len(action["data"]["participants"]) == 1:
                self._close_tags(c, state, action)
        elif kind == "harpy_tag_agreement":
            if (
                answer.flag is None
                or answer.options
                or answer.denied
                or answer.fields
                or answer.number is not None
                or answer.member
            ):
                raise WorkflowError("Record only your own actual agreement or disagreement.")
            meta = action["data"]["harpy_defeat"]
            meta["tag_agreements"][row["actor_id"]] = answer.flag
            if not any(
                x["kind"] == "harpy_tag_agreement" for x in self.game.pending(c, action["id"])
            ):
                if all(meta["tag_agreements"].values()):
                    self._close_tags(c, state, action)
                else:
                    meta.pop("tag_candidate", None)
                    self.game.request(c, action, declared.gm_controller, "harpy_tag_select")
        elif kind == "harpy_tag_resolution":
            if (
                int(row["actor_id"]) != declared.controller
                or len(answer.options) != 1
                or answer.options[0] not in ("reject", "embrace")
            ):
                raise WorkflowError("Only this actual Harpy's human resolves the repeated Tag.")
            tag_id = json.loads(row["body_json"])["tag"]
            if answer.options == ("embrace",):
                actor_rules.embrace(state, declared.actor, tag_id, answer.denied)
            else:
                if answer.denied:
                    raise WorkflowError("A deferred rejection does not replace an Identity.")
                from girlframe.engine.m3_tag_permissions import can_reject

                if not can_reject(state, declared.actor, tag_id):
                    raise WorkflowError(
                        "The original Beneath locker must consent before rejecting this retained "
                        "Tag."
                    )
                from girlframe.services.m3_tag_permissions import PermissionService

                PermissionService(self.store).authorize_rejection(
                    c,
                    viewer,
                    state,
                    declared.actor,
                    tag_id,
                )
                actor_rules.defer_rejection(state, declared.actor, tag_id)
                self.game.obligation(
                    state,
                    action,
                    "actor_reject_tag",
                    declared.controller,
                    actor=declared.actor.model_dump_json(),
                    tag=tag_id,
                )
            self._results(c, action)
        elif kind.startswith("harpy_"):
            self._outcome(c, state, action, row, answer)
        else:
            raise WorkflowError("Use this actual Harpy Defeat's source-owned choice.")

    def _ref(self, state: GameState, declared: "Declaration", token: str) -> ActorRef:
        value = next((x.actor for x in declared.cast.roles if x.actor.token == token), None)
        if value is None:
            raise WorkflowError("Choose an actual original actor from this source scene.")
        return value

    def _finish(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        if self.game.pending(c, action["id"]):
            return
        declared = self._declaration(c, action)
        action["state"] = "complete"
        self.game.queue(
            c,
            action,
            "outcome",
            dict(
                play="harpy_defeat",
                callsign=action["data"].get("harpy_label", "Harpy"),
                receipt=action["data"]["receipt"],
                total=action["data"]["result"].get("total"),
                tier=action["data"]["result"].get("tier"),
                actor=declared.actor.model_dump(mode="json"),
            ),
        )

    def _outcome(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        row: dict[str, Any],
        answer: ChoiceAnswer,
    ) -> None:
        from girlframe.engine.m3_actor_bonds import change
        from girlframe.engine.m3_harpy_defeat_state import DefeatEffect, Rift

        declared = self._declaration(c, action)
        source = action["data"]["response_event"]
        kind = row["kind"]
        existing = next((x for x in state.harpy_defeats if x.action == action["id"]), None)
        if kind == "harpy_defeat_select":
            allowed = {
                "mid": ("message", "rift"),
                "high": ("kidnap", "foundation", "plead"),
                "low": ("death", "shutdown", "rescue"),
            }[action["data"]["result"]["tier"]]
            if (
                int(row["actor_id"]) != declared.controller
                or existing is not None
                or len(answer.options) != 1
                or answer.options[0] not in allowed
                or not answer.text.strip()
            ):
                raise WorkflowError(
                    "Choose one printed result for this actual Harpy and describe it."
                )
            choice = answer.options[0]
            effect = DefeatEffect.model_validate(
                dict(
                    id=str(uuid4()),
                    action=action["id"],
                    work=declared.work,
                    actor=declared.actor,
                    frame_instance=declared.frame_instance,
                    source_event=source,
                    tier=action["data"]["result"]["tier"],
                    choice=choice,
                    account=answer.text.strip(),
                    source_cast=declared.cast,
                )
            )
            if choice in ("message", "plead", "kidnap"):
                girl = self._ref(state, declared, answer.fields.get("girl", ""))
                if girl not in rules.girls(state, declared.cast):
                    raise WorkflowError("Choose an actual current original Girl in this scene.")
                effect = effect.model_copy(update={"girl": girl})
                if choice == "message":
                    _copy(state, change(state, declared.actor, girl, 1, source))
                    _copy(state, rules.escape(state, declared.actor, source))
                    effect = effect.model_copy(
                        update={"escaped": True, "departed": (declared.actor,)}
                    )
                elif choice == "plead":
                    effect = effect.model_copy(update={"phase": "awaiting_girl"})
                    self.game.request(
                        c, action, int(girl.entity), "harpy_girl_plea", {"effect": effect.id}
                    )
                else:
                    _copy(
                        state,
                        rules.kidnap(
                            state,
                            declared.actor,
                            girl,
                            profiles(c, self.store.campaign_id),
                            source,
                            answer.text,
                        ),
                    )
                    effect = effect.model_copy(
                        update={"escaped": True, "departed": (girl, declared.actor)}
                    )
            elif choice == "rift":
                state.void_rifts.append(
                    Rift(
                        id=str(uuid4()),
                        owner=declared.actor,
                        action=action["id"],
                        scene=action["scene_id"],
                        source_event=source,
                        description=answer.text.strip(),
                    )
                )
                _copy(state, rules.escape(state, declared.actor, source))
                effect = effect.model_copy(update={"escaped": True, "departed": (declared.actor,)})
            elif choice == "rescue":
                rescuer = self._ref(state, declared, answer.fields.get("rescuer", ""))
                if rescuer == declared.actor:
                    raise WorkflowError(
                        "Another actual Harpy in this scene must perform the rescue."
                    )
                self._runtime(c, state, rescuer)
                rescuer_view = resolve(
                    state,
                    rescuer,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                rescuer_body = rules.harpy(state, rescuer)
                if (
                    rescuer_view.cell is None
                    or rescuer_body.body_incapacitated
                    or rescuer_body.subsumed
                    or not rescuer_body.vitals_active
                    or rescuer_body.custody != "free"
                ):
                    raise WorkflowError(
                        "The actual scene rescuer needs an active, accessible body."
                    )
                _copy(state, rules.escape(state, rescuer, source))
                _copy(state, rules.escape(state, declared.actor, source))
                effect = effect.model_copy(
                    update={
                        "rescuer": rescuer,
                        "escaped": True,
                        "departed": (rescuer, declared.actor),
                    }
                )
            elif choice == "death":
                _, body, _ = self._source(c, declared.work)
                actual = DamageRequired.model_validate(body["requirement"]).opponent
                proposed_killer = answer.fields.get("killer", "")
                killer = self._ref(state, declared, proposed_killer) if proposed_killer else actual
                if actual is not None and killer != actual:
                    raise WorkflowError(
                        "This source identifies the actual killer; do not substitute another actor."
                    )
                tag = answer.fields.get("tag", "").strip()
                if not tag:
                    raise WorkflowError(
                        "The actual dying Harpy chooses the Tag inflicted on her killer."
                    )
                effect = effect.model_copy(
                    update={"killer": killer, "tag": tag, "phase": "awaiting_killer"}
                )
                self.game.request(
                    c, action, declared.gm_controller, "harpy_killer_fact", {"effect": effect.id}
                )
            else:
                cut = choice == "shutdown" and answer.flag is True
                if cut:
                    _copy(state, rules.shutdown(state, declared.actor, source, cut_link=True))
                    effect = effect.model_copy(
                        update={"cut_link": True, "phase": "awaiting_physical"}
                    )
                    girl_assets = tuple(
                        x for x in rules.assets(state, declared.actor) if x.family == "girl"
                    )
                    if girl_assets and all(x.damaged for x in girl_assets):
                        _, work_body, _ = self._source(c, declared.work)
                        foe = DamageRequired.model_validate(work_body["requirement"]).opponent
                        try:
                            if foe is None:
                                raise ValueError("No original actual foe source")
                            resolve(
                                state,
                                foe,
                                profiles(c, self.store.campaign_id),
                                require_current_profile=False,
                            )
                        except ValueError:
                            self.game.request(
                                c,
                                action,
                                declared.gm_controller,
                                "harpy_foe_fact",
                                {"effect": effect.id},
                            )
                        else:
                            from girlframe.engine.m3_actor_bonds import make_helpless

                            _copy(state, make_helpless(state, declared.actor, foe, source))
                            effect = effect.model_copy(
                                update={"phase": "complete", "factual_source": source}
                            )
                else:
                    _copy(state, rules.shutdown(state, declared.actor, source, cut_link=False))
                    effect = effect.model_copy(update={"phase": "awaiting_captor"})
                    self.game.request(
                        c,
                        action,
                        declared.gm_controller,
                        "harpy_capture_fact",
                        {"effect": effect.id},
                    )
            state.harpy_defeats.append(effect)
            action["data"]["result"]["harpy_effect"] = effect.id
        elif existing is None:
            raise WorkflowError("Recover the actual original Harpy's selected source effect.")
        elif kind == "harpy_girl_plea":
            responding_girl = existing.girl
            girl = responding_girl if responding_girl is not None else declared.actor
            if (
                girl is None
                or row["actor_id"] != girl.entity
                or len(answer.options) != 1
                or answer.options[0] not in ("come", "refuse")
                or not answer.text.strip()
            ):
                raise WorkflowError(
                    "The actual original Girl must choose and describe her own response."
                )
            if girl not in rules.girls(state, declared.cast):
                raise WorkflowError("The original Girl ended; no replacement can answer her plea.")
            departed: tuple[ActorRef, ...] = (declared.actor,)
            if answer.options == ("refuse",):
                tag = answer.fields.get("tag", "").strip()
                if not tag:
                    raise WorkflowError(
                        "The refusing Girl chooses the actual Tag she gives this Harpy."
                    )
                from girlframe.engine.m2 import shift_status

                shift_status(state, int(girl.entity), 1)
                _copy(
                    state,
                    rules.give_tag(
                        state,
                        declared.actor,
                        girl,
                        tag,
                        source,
                        str(uuid4()),
                        tuple(action["data"]["participants"]),
                    ),
                )
            else:
                from girlframe.engine.m3_physical import extract

                placement = next((x for x in state.placements if x.actor == girl), None)
                if placement is None:
                    raise WorkflowError("Record this Girl's actual physical placement first.")
                physical = resolve(
                    state, girl, profiles(c, self.store.campaign_id), require_current_profile=False
                )
                own_frame = (
                    physical.piloting is True
                    and placement.occupied_frame_owner is None
                    and physical.occupied_frame_instance == placement.frame_instance
                )
                if placement.mode != "outside_frame" and not own_frame:
                    _copy(
                        state,
                        extract(
                            state, profiles(c, self.store.campaign_id), girl, source, answer.text
                        ),
                    )
                    placement = next(x for x in state.placements if x.actor == girl)
                movement: dict[str, Any] = dict(
                    girl_cell=None, source_event=source, account=answer.text
                )
                if own_frame:
                    movement["frame_cell"] = None
                moved = placement.model_copy(update=movement)
                state.placements = [moved if x.actor == girl else x for x in state.placements]
                from girlframe.engine.m3_battle import end_actor_casts

                _copy(state, end_actor_casts(state, girl, source))
                departed = (declared.actor, girl)
            _copy(state, rules.escape(state, declared.actor, source))
            revised = existing.model_copy(
                update={
                    "phase": "complete",
                    "response_event": source,
                    "response": answer.text,
                    "escaped": True,
                    "departed": departed,
                }
            )
            state.harpy_defeats = [
                revised if x.id == existing.id else x for x in state.harpy_defeats
            ]
        elif kind == "harpy_foe_fact":
            if (
                int(row["actor_id"]) != declared.gm_controller
                or answer.flag is not True
                or not answer.text.strip()
            ):
                raise WorkflowError(
                    "The actual source judge must identify the original body's actual foe."
                )
            foe = self._ref(state, declared, answer.fields.get("foe", ""))
            resolve(state, foe, profiles(c, self.store.campaign_id), require_current_profile=False)
            girl_assets = tuple(
                x for x in rules.assets(state, declared.actor) if x.family == "girl"
            )
            if not (
                existing
                and existing.cut_link
                and not rules.harpy(state, declared.actor).linked
                and girl_assets
                and all(x.damaged for x in girl_assets)
            ):
                raise WorkflowError(
                    "Recover the actual all-Girl-Assets-damaged outside-body source."
                )
            from girlframe.engine.m3_actor_bonds import make_helpless

            _copy(state, make_helpless(state, declared.actor, foe, source))
            state.harpy_defeats = [
                x.model_copy(
                    update={
                        "phase": "complete",
                        "factual_source": source,
                        "response_event": source,
                        "response": answer.text,
                    }
                )
                if x.id == existing.id
                else x
                for x in state.harpy_defeats
            ]
        elif kind in ("harpy_killer_fact", "harpy_capture_fact"):
            if (
                int(row["actor_id"]) != declared.gm_controller
                or not answer.text.strip()
                or answer.flag is not True
            ):
                raise WorkflowError(
                    "The actual source adjudicator must record and confirm the factual killer "
                    "or custody."
                )
            if kind == "harpy_killer_fact":
                killer = existing.killer or self._ref(
                    state, declared, answer.fields.get("killer", "")
                )
                assert existing.tag is not None
                tag_id = str(uuid4())
                ended = ended_actor_source(self.game, c, state, killer)
                if ended is None:
                    _copy(
                        state,
                        rules.give_tag(
                            state,
                            killer,
                            declared.actor,
                            existing.tag,
                            source,
                            tag_id,
                            tuple(action["data"]["participants"]),
                        ),
                    )
                own_ending = ended_actor_source(self.game, c, state, declared.actor)
                if own_ending is None:
                    _copy(state, rules.die(state, declared.actor, source))
                values: dict[str, Any] = dict(
                    tag_id=tag_id,
                    killer=killer,
                    tag_recipient=killer,
                    archived_tag=ended is not None,
                    tag_applied_event=source if ended is None else None,
                    departed=(declared.actor,),
                )
            else:
                captor = self._ref(state, declared, answer.fields.get("captor", ""))
                view = resolve(
                    state,
                    captor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                harpy_body = rules.harpy(state, declared.actor)
                if harpy_body.subsumed or (
                    harpy_body.custody != "free" and harpy_body.custodian != captor
                ):
                    raise WorkflowError(
                        "Resolve actual extraction or the existing custodian before a new capture."
                    )
                npc = (
                    next((x for x in state.world.npcs if x.id == captor.entity), None)
                    if state.world and captor.kind == "npc"
                    else None
                )
                if (
                    view.cell is None
                    or harpy_body.cell is None
                    or view.cell != harpy_body.cell
                    or not (
                        captor.kind in ("pilot", "handler")
                        or (npc and npc.employment == "foundation")
                    )
                ):
                    raise WorkflowError(
                        "Choose the actual present Foundation captor; no capture or location is "
                        "invented."
                    )
                _copy(
                    state,
                    rules.update(
                        state,
                        declared.actor,
                        custody="captured",
                        custodian=captor,
                        custody_event=source,
                    ),
                )
                values = dict(captor=captor)
            revised = existing.model_copy(
                update={
                    **values,
                    "phase": "complete",
                    "response_event": source,
                    "response": answer.text,
                    "factual_source": source,
                }
            )
            state.harpy_defeats = [
                revised if x.id == existing.id else x for x in state.harpy_defeats
            ]
        else:
            raise WorkflowError("Use the actual source-owned Harpy consequence response.")
        self._finish(c, state, action)

    def _complete_work(
        self,
        c: Connection,
        action: dict[str, Any],
        event: str,
        viewer: GuildViewer | None,
        key: str,
    ) -> None:
        from girlframe.services.m3_battle import complete_damage_work, synchronize_casts

        declared = self._declaration(c, action)
        row, body, _ = self._source(c, declared.work)
        table = t.m3["m3_required_work"]
        c.execute(
            table.insert().values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "state", "body_json", "event_id")
                },
                revision=row["revision"] + 1,
                state="resolved",
                event_id=event,
                body_json=json.dumps(
                    body | {"defeat_action": action["id"], "completion_event": event},
                    sort_keys=True,
                ),
            )
        )
        synchronize_casts(self.game, c, event)
        complete_damage_work(self.game, c, row, event, viewer, key)

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, answer: ChoiceAnswer
    ) -> dict[str, Any]:
        answer = ChoiceAnswer.model_validate_json(answer.model_dump_json())

        def access(c: Connection) -> None:
            row, action = self._owned(c, viewer, identity)
            self.authorize(c, viewer, action)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, action = self._owned(c, viewer, identity)
            if (
                row["revision"] != revision
                or row["state"] != "pending"
                or action["state"] in ("complete", "aborted")
            ):
                raise WorkflowError("STALE_HARPY_CHOICE: reopen the actual original response.")
            state, _, _ = self._current(c, action)
            lock = self.game.lock(c, action["channel_id"])
            if lock is None or lock["state"] != "held":
                raise WorkflowError("Restore the actual source chat lock first.")
            choices = t.m2["m2_choices"]
            c.execute(
                choices.update()
                .where(choices.c.campaign_id == self.store.campaign_id, choices.c.id == identity)
                .values(state="answered", revision=revision + 1)
            )
            action["data"]["choices"][row["kind"] + ":" + row["actor_id"]] = answer.model_dump(
                mode="json"
            )
            event = str(uuid4())
            action["data"]["response_event"] = event
            self._apply(c, state, action, row, answer, viewer)
            self.game.save_action(c, action)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_defeat_choice",
                state,
                event_id=event,
                action_id=action["id"],
                choice_id=identity,
            )
            c.execute(
                t.m2["m2_responses"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    choice_id=identity,
                    actor_id=str(viewer.user_id),
                    event_id=event,
                    answer_json=answer.model_dump_json(),
                )
            )
            from girlframe.services.m3_harpy_rest import synchronize_endings

            synchronize_endings(self.game, c, event)
            if action["state"] == "complete":
                self._complete_work(c, action, event, viewer, key)
            return dict(action_id=action["id"], state=action["state"], choice_id=identity)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_defeat_choice",
                dict(id=identity, revision=revision, answer=answer.model_dump(mode="json")),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _owned(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        choices = t.m2["m2_choices"]
        row = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == self.store.campaign_id, choices.c.id == identity
                )
            )
            .mappings()
            .first()
        )
        if row is None or row["actor_id"] != str(viewer.user_id):
            raise WorkflowError("This original Harpy choice belongs to another actual human.")
        action = self.game.action(c, row["action_id"])
        self.authorize(c, viewer, action, read=row["state"] != "pending")
        return dict(row), action

    def inspect(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            action = self.game.action(c, identity)
            declared = self.authorize(c, viewer, action, read=True)
            canonical = c.scalar(
                sa.select(t.m2["m2_receipts"].c.body_json).where(
                    t.m2["m2_receipts"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_receipts"].c.action_id == identity,
                )
            )
            if canonical is not None and json.loads(canonical) != action["data"].get("receipt"):
                raise WorkflowError(
                    "Recover the actual immutable Harpy receipt; no reroll is allowed."
                )
            return dict(
                id=identity,
                action_id=identity,
                state=action["state"],
                revision=action["revision"],
                play="harpy_defeat",
                actor=declared.actor.model_dump(mode="json"),
                receipt=action["data"].get("receipt"),
                result=action["data"]["result"],
                pending=[
                    dict(id=x["id"], kind=x["kind"], owner=int(x["actor_id"]))
                    for x in self.game.pending(c, identity)
                ],
            )

    def decision(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, action = self._owned(c, viewer, identity)
            state = load_state(c, self.store.campaign_id)
            declared = self._declaration(c, action)
            body = rules.harpy(state, declared.actor)
            from girlframe.services.m3_battle import _visible
            from girlframe.services.m3_tag_markers import projection

            actors = []
            for role in declared.cast.roles:
                if role.actor == declared.actor or not (
                    _visible(state, role.actor, viewer.user_id)
                    or (
                        viewer.user_id == state.handler
                        and row["kind"]
                        in ("harpy_killer_fact", "harpy_capture_fact", "harpy_foe_fact")
                    )
                ):
                    continue
                try:
                    view = resolve(
                        state,
                        role.actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                except ValueError:
                    continue
                actors.append(
                    dict(
                        ref=role.actor.model_dump(mode="json"),
                        token=role.actor.token,
                        label=view.label,
                        rules=view.rules,
                        girl=view.girl,
                    )
                )
            from girlframe.engine.m3_tag_permissions import can_reject

            selected_tag = json.loads(row["body_json"]).get("tag")
            return dict(
                harpy_defeat=True,
                id=identity,
                action_id=action["id"],
                revision=row["revision"],
                kind=row["kind"],
                state=row["state"],
                body=json.loads(row["body_json"]),
                tier=action["data"]["result"].get("tier"),
                tags=[
                    dict(id=x.id, label=x.label)
                    for x in body.tags
                    if viewer.user_id in x.observers and x.scene_used != action["scene_id"]
                ],
                markers=projection(self.game, c, state, action, viewer.user_id)
                if row["kind"] == "tag_window"
                else [],
                identities=[dict(id=x.id, name=x.name) for x in body.identities if not x.protected],
                replace_count=1 if len(body.identities) >= 4 else 0,
                girls=[
                    dict(
                        ref=x.model_dump(mode="json"),
                        token=x.token,
                        label=state.sheets[x.entity].callsign,
                    )
                    for x in rules.girls(state, declared.cast)
                ],
                receipt=action["data"].get("receipt"),
                actors=actors,
                can_reject=can_reject(state, declared.actor, selected_tag)
                if selected_tag
                else True,
                actor=declared.actor.model_dump(mode="json"),
                tag_candidates=action["data"]["harpy_defeat"].get("tag_candidates", []),
                has_source_killer=DamageRequired.model_validate(
                    self._source(c, declared.work, pending=False)[1]["requirement"]
                ).opponent
                is not None,
                physical_controls=body.subsumed or not body.vitals_active,
                needs_killer=any(
                    x.action == action["id"] and x.choice == "death" and x.killer is None
                    for x in state.harpy_defeats
                ),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        canon = load_state(c, self.store.campaign_id)
        tasks: list[dict[str, Any]] = []
        table = t.m3["m3_required_work"]
        latest = {
            x["id"]: dict(x)
            for x in c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id, table.c.kind == "harpy_defeat"
                )
                .order_by(table.c.revision)
            ).mappings()
        }
        for row in latest.values():
            if row["state"] == "resolved" or row["owner_id"] != str(viewer.user_id):
                continue
            action = c.scalar(
                sa.select(t.m2["m2_actions"].c.id).where(
                    t.m2["m2_actions"].c.campaign_id == self.store.campaign_id,
                    sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.harpy_defeat.work")
                    == row["id"],
                )
            )
            tasks.append(
                dict(
                    id=row["id"],
                    kind="harpy_defeat",
                    label="Resolve your actual Harpy Defeat",
                    can_act=True,
                    state="pending",
                    action=action,
                )
            )
        for setup in canon.harpy_setups:
            if setup.state == "proposed" and viewer.user_id in (setup.owner, setup.handler):
                tasks.append(
                    dict(
                        id=setup.id,
                        kind="harpy_setup",
                        label="Review actual native Harpy facts",
                        state=setup.state,
                        can_act=viewer.user_id == setup.handler,
                    )
                )
        for value in canon.harpy_travels:
            if value.state == "proposed" and viewer.user_id in (value.controller, value.judge):
                tasks.append(
                    dict(
                        id=value.id,
                        kind="harpy_route",
                        label="Review actual Voidspace navigation",
                        state=value.state,
                        can_act=viewer.user_id == value.judge,
                    )
                )
            elif value.state == "offstage" and viewer.user_id == value.controller:
                tasks.append(
                    dict(
                        id=value.id,
                        kind="harpy_return",
                        label="Propose this actual body's return",
                        state=value.state,
                        can_act=True,
                    )
                )
        for effect in canon.harpy_defeats:
            if effect.escaped:
                for actor in effect.departed:
                    try:
                        actual = resolve(
                            canon,
                            actor,
                            profiles(c, self.store.campaign_id),
                            require_current_profile=False,
                        )
                    except ValueError:
                        continue
                    if (
                        actual.controller == viewer.user_id
                        and actual.cell is None
                        and rules.offstage_travel(canon, actor) is None
                    ):
                        tasks.append(
                            dict(
                                id=effect.id + ":" + actor.token,
                                kind="harpy_escape",
                                label="Propose your escaped body's actual return",
                                state="offstage",
                                can_act=True,
                                actor=actor.model_dump(mode="json"),
                                effect=effect.id,
                            )
                        )
            if (
                effect.cut_link
                and effect.phase == "awaiting_physical"
                and rules.controller(canon, effect.actor) == viewer.user_id
            ):
                tasks.append(
                    dict(
                        id=effect.id,
                        kind="harpy_fight",
                        label="Continue fighting until actually Helpless",
                        state="pending",
                        can_act=not rules.fight_required(canon, effect.actor),
                    )
                )
            if (
                effect.choice == "message"
                and effect.girl is not None
                and viewer.user_id
                in (rules.controller(canon, effect.actor), int(effect.girl.entity))
            ):
                tasks.append(
                    dict(
                        id=effect.id,
                        kind="harpy_message",
                        label="Read actual final Harpy comms",
                        state="complete",
                        can_act=True,
                    )
                )
        for portal in canon.void_rifts:
            if not portal.open:
                continue
            cast = next((x for x in canon.scene_casts if x.id == portal.scene and x.open), None)
            if rules.controller(canon, portal.owner) == viewer.user_id or (
                cast is not None and any(x.controller == viewer.user_id for x in cast.roles)
            ):
                tasks.append(
                    dict(
                        id=portal.id,
                        kind="harpy_rift",
                        label="Open Voidspace Rift: follow or owner close",
                        state="open",
                        can_act=True,
                    )
                )
        return tasks

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)

    def task(self, viewer: GuildViewer, kind: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            task = next(
                (x for x in self._tasks(c, viewer) if x["kind"] == kind and x["id"] == identity),
                None,
            )
            if task is None:
                raise WorkflowError(
                    "This source-owned Harpy task belongs to another original participant."
                )
            canon = load_state(c, self.store.campaign_id)
            result = task | dict(revision=canon.revision)
            if kind == "harpy_setup":
                setup = next(x for x in canon.harpy_setups if x.id == identity)
                result.update(setup=setup.model_dump(mode="json"))
            elif kind in ("harpy_return", "harpy_route"):
                route = next(x for x in canon.harpy_travels if x.id == identity)
                self._travel_proof(c, route)
                result.update(route=route.model_dump(mode="json"))
            elif kind == "harpy_message":
                effect = next(x for x in canon.harpy_defeats if x.id == identity)
                result.update(account=effect.account)
            elif kind == "harpy_rift":
                portal = next(x for x in canon.void_rifts if x.id == identity)
                cast = next((x for x in canon.scene_casts if x.id == portal.scene and x.open), None)
                actors = []
                if cast is not None:
                    for role in cast.roles:
                        if role.controller != viewer.user_id:
                            continue
                        try:
                            view = resolve(
                                canon,
                                role.actor,
                                profiles(c, self.store.campaign_id),
                                require_current_profile=False,
                            )
                        except ValueError:
                            continue
                        actors.append(
                            dict(
                                ref=role.actor.model_dump(mode="json"),
                                token=role.actor.token,
                                label=view.label,
                            )
                        )
                result.update(
                    rift=portal.model_dump(mode="json"),
                    actors=actors,
                    can_close=rules.controller(canon, portal.owner) == viewer.user_id,
                )
            return result

    def finish_fight(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            self.game.unpaused(c)
            canon = load_state(c, self.store.campaign_id)
            effect = next((x for x in canon.harpy_defeats if x.id == identity), None)
            if (
                effect is None
                or not effect.cut_link
                or effect.phase != "awaiting_physical"
                or canon.revision != expected
                or rules.controller(canon, effect.actor) != viewer.user_id
            ):
                raise WorkflowError("Use the actual original Harpy's continuing-fight consequence.")
            from girlframe.engine.m3_actor_bonds import is_helpless

            if not is_helpless(canon, effect.actor):
                raise WorkflowError(
                    "This original body is not actually Helpless yet; continue the fight."
                )
            event = str(uuid4())
            canon.harpy_defeats = [
                x.model_copy(update={"phase": "complete", "response_event": event})
                if x.id == identity
                else x
                for x in canon.harpy_defeats
            ]
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_fight_completed",
                canon,
                event_id=event,
                effect=identity,
            )
            return dict(id=identity, state="complete")

        return self.store._write(
            viewer,
            key,
            "m3.harpy_fight_completed",
            dict(id=identity, expected=expected),
            operation,
            auto_audit=False,
        )

    def _travel_proof(self, c: Connection, value: "Travel") -> "Travel":
        from girlframe.engine.m3_harpy_defeat_state import Travel

        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        state = GameState.model_validate_json(raw) if raw else None
        original = (
            next((x for x in state.harpy_travels if x.id == value.id), None) if state else None
        )
        fields = tuple(
            x for x in Travel.model_fields if x not in ("state", "response_event", "review")
        )
        actor = c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.id == value.source_event,
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind == "m3.harpy_route_proposed",
            )
        )
        if actor is None and value.off_duty_action is not None and state is not None:
            rest = next(
                (
                    x
                    for x in state.harpy_rests
                    if x.route == value.id
                    and x.action == value.off_duty_action
                    and x.source_event == value.source_event
                    and x.actor == value.actor
                    and x.controller == value.controller
                ),
                None,
            )
            responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
            if rest is not None:
                actor = c.scalar(
                    sa.select(responses.c.actor_id)
                    .join(
                        choices,
                        sa.and_(
                            choices.c.campaign_id == responses.c.campaign_id,
                            choices.c.id == responses.c.choice_id,
                        ),
                    )
                    .where(
                        responses.c.campaign_id == self.store.campaign_id,
                        responses.c.event_id == value.source_event,
                        choices.c.action_id == value.off_duty_action,
                        choices.c.kind == "harpy_off_duty_hide",
                    )
                )
        if (
            original is None
            or actor != str(value.controller)
            or any(getattr(value, k) != getattr(original, k) for k in fields)
        ):
            raise WorkflowError("Recover the actual original body's owned navigation proposal.")
        return original

    def propose_route(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        actor: ActorRef,
        *,
        rift: str | None = None,
        escape_effect: str | None = None,
        return_of: str | None = None,
        destination: tuple[int, int] | None = None,
        account: str,
        navigation: str,
    ) -> dict[str, Any]:
        from girlframe.engine.m3_harpy_defeat_state import Travel
        from girlframe.services.m3_actor_plays import ActorPlayService

        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)

        def operation(c: Connection) -> dict[str, Any]:
            chosen_rift, chosen_escape = rift, escape_effect
            chosen_rest = None
            self.game.unpaused(c)
            canon = load_state(c, self.store.campaign_id)
            view = resolve(
                canon, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if view.controller != viewer.user_id or canon.revision != expected:
                raise WorkflowError(
                    "Only the actual original body's controller proposes its route."
                )
            if not account.strip() or not navigation.strip() or rules.fight_required(canon, actor):
                raise WorkflowError(
                    "Record actual navigation; a source-required fight must continue until "
                    "Helpless."
                )
            if view.subsumed or view.vitals_active is False or view.custody not in (None, "free"):
                raise WorkflowError(
                    "Actual custody and extraction must resolve before this body can travel."
                )
            if any(x.active and actor in (x.traveler, x.supervisor) for x in canon.escort_journeys):
                raise WorkflowError("Resolve the actual escorted journey before another route.")
            if any(x.actor == actor and x.state == "proposed" for x in canon.harpy_travels):
                raise WorkflowError(
                    "The original body already has an actual pending navigation proposal."
                )
            prior = rules.offstage_travel(canon, actor)
            gm, appointment = MedicalService(self.store)._handler(c)
            adjudicator = None
            if return_of is not None:
                if prior is None or prior.id != return_of:
                    raise WorkflowError(
                        "Return only this exact original body's actual offstage journey."
                    )
                self._travel_proof(c, prior)
                chosen_rift, chosen_escape = prior.rift, prior.escape_effect
                chosen_rest = prior.off_duty_action
                travels_frame, instance = prior.travels_frame, prior.frame_instance
                if (
                    destination is None
                    or canon.world is None
                    or not (
                        canon.world.board.minimum[0]
                        <= destination[0]
                        <= canon.world.board.maximum[0]
                        and canon.world.board.minimum[1]
                        <= destination[1]
                        <= canon.world.board.maximum[1]
                    )
                ):
                    raise WorkflowError("Name the actual reviewed return cell on this map.")
            else:
                if prior is not None:
                    raise WorkflowError(
                        "This exact body is already offstage; propose its actual return."
                    )
                if view.inside_frame is True and view.piloting is not True:
                    raise WorkflowError(
                        "Use actual extraction or the actual pilot's route, not another body's "
                        "Frame."
                    )
                travels_frame, instance = view.piloting is True, view.frame_instance
                if chosen_rift is not None:
                    portal = next(
                        (x for x in canon.void_rifts if x.id == chosen_rift and x.open), None
                    )
                    cast = next(
                        (
                            x
                            for x in canon.scene_casts
                            if portal and x.id == portal.scene and x.open
                        ),
                        None,
                    )
                    if (
                        portal is None
                        or cast is None
                        or not any(x.actor == actor for x in cast.roles)
                    ):
                        raise WorkflowError(
                            "The actual open Rift and original body must share the real scene."
                        )
                    judge = ActorPlayService(self.game)._judge(c, canon, cast, actor)
                    gm, adjudicator = judge.controller, judge.ref
                    if view.cell is None:
                        raise WorkflowError(
                            "Recover actual physical access to the Rift before following."
                        )
                else:
                    effect = next((x for x in canon.harpy_defeats if x.id == chosen_escape), None)
                    if effect is None or not effect.escaped or actor not in effect.departed:
                        raise WorkflowError(
                            "Only an actual printed escaped original may propose this return."
                        )
                    if destination is None:
                        raise WorkflowError("Propose the actual known return destination.")
                    # A printed escape already moved the body offstage; this reviewed
                    # route returns it, without inventing an intermediate location.
                    travels_frame = view.inside_frame is True
            event, identity = str(uuid4()), str(uuid4())
            value = Travel(
                id=identity,
                actor=actor,
                controller=viewer.user_id,
                source_event=event,
                source_sha256=view.source_sha256,
                rift=chosen_rift,
                escape_effect=chosen_escape,
                off_duty_action=chosen_rest,
                frame_instance=instance,
                travels_frame=travels_frame,
                destination=destination,
                account=account.strip(),
                navigation=navigation.strip(),
                judge=gm,
                adjudicator=adjudicator,
                appointment=appointment,
                return_of=return_of,
            )
            canon.harpy_travels.append(value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_route_proposed",
                canon,
                event_id=event,
                route=identity,
            )
            return dict(id=identity, state="proposed")

        return self.store._write(
            viewer,
            key,
            "m3.harpy_route_proposed",
            dict(
                actor=actor.model_dump(mode="json"),
                rift=rift,
                escape_effect=escape_effect,
                return_of=return_of,
                destination=destination,
                account=account,
                navigation=navigation,
                expected=expected,
            ),
            operation,
            authorize=access,
            auto_audit=False,
        )

    def review_route(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        *,
        allow: bool,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            canon = load_state(c, self.store.campaign_id)
            value = next((x for x in canon.harpy_travels if x.id == identity), None)
            if (
                value is None
                or value.state != "proposed"
                or viewer.user_id != value.judge
                or canon.revision != expected
                or not account.strip()
            ):
                raise WorkflowError(
                    "The actual source adjudicator owns this exact navigation review."
                )
            self._travel_proof(c, value)
            if MedicalService(self.store)._handler(c)[1] != value.appointment:
                raise WorkflowError(
                    "The original campaign appointment changed; recover this actual route."
                )
            if allow:
                view = resolve(
                    canon,
                    value.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if view.controller != value.controller or view.source_sha256 != value.source_sha256:
                    raise WorkflowError(
                        "The actual original body's physical/resources source changed; propose "
                        "a fresh route."
                    )
                if (
                    allow
                    and value.rift is not None
                    and value.return_of is None
                    and not any(x.id == value.rift and x.open for x in canon.void_rifts)
                ):
                    raise WorkflowError("This source Rift closed before the actual crossing.")
                if allow and any(
                    x.active and value.actor in (x.traveler, x.supervisor)
                    for x in canon.escort_journeys
                ):
                    raise WorkflowError("The actual escorted journey conflicts with this route.")
            event = str(uuid4())
            stage = (
                "rejected"
                if not allow
                else "returned"
                if value.destination is not None
                else "offstage"
            )
            revised = value.model_copy(
                update={"state": stage, "response_event": event, "review": account.strip()}
            )
            canon.harpy_travels = [revised if x.id == identity else x for x in canon.harpy_travels]
            if allow:
                if value.return_of:
                    canon.harpy_travels = [
                        x.model_copy(update={"state": "returned", "response_event": event})
                        if x.id == value.return_of
                        else x
                        for x in canon.harpy_travels
                    ]
                if value.actor.kind == "pilot":
                    placement = next((x for x in canon.placements if x.actor == value.actor), None)
                    if placement is None:
                        raise WorkflowError(
                            "Recover the original actual Girl's physical placement."
                        )
                    values = dict(girl_cell=value.destination, source_event=event, account=account)
                    if value.travels_frame:
                        values["frame_cell"] = value.destination
                    canon.placements = [
                        x.model_copy(update=values) if x.actor == value.actor else x
                        for x in canon.placements
                    ]
                elif value.actor.kind == "external_pilot" and (
                    any(x.id == value.actor.entity for x in canon.harpy_states)
                    or any(x.id == value.actor.entity for x in canon.native_harpies)
                ):
                    updates = dict(cell=value.destination, condition_event=event)
                    if value.travels_frame:
                        updates["frame_cell"] = value.destination
                    _copy(canon, rules.update(canon, value.actor, **updates))
                elif value.destination is not None and canon.world is not None:
                    field = {"npc": "npcs", "gorgon": "gorgons", "external_pilot": "pilots"}.get(
                        value.actor.kind
                    )
                    if field:
                        canon.world = canon.world.model_copy(
                            update={
                                field: tuple(
                                    x.model_copy(update={"cell": value.destination})
                                    if x.id == value.actor.entity
                                    else x
                                    for x in getattr(canon.world, field)
                                )
                            }
                        )
                    elif value.actor.kind == "handler":
                        canon.facts.append(
                            dict(
                                kind="recorded_handler_recovery_position",
                                actor=value.actor.model_dump_json(),
                                cell=json.dumps(value.destination),
                            )
                        )
                if stage == "offstage":
                    from girlframe.engine.m3_battle import end_actor_casts

                    _copy(canon, end_actor_casts(canon, value.actor, event))
            if value.off_duty_action is not None:
                from girlframe.services.m3_harpy_rest import complete_route

                complete_route(self.game, c, canon, revised, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_route_reviewed",
                canon,
                event_id=event,
                route=identity,
            )
            if allow and stage == "offstage":
                from girlframe.services.m3_battle import synchronize_casts

                synchronize_casts(self.game, c, event)
            return dict(id=identity, state=stage)

        return self.store._write(
            viewer,
            key,
            "m3.harpy_route_reviewed",
            dict(id=identity, expected=expected, allow=allow, account=account),
            operation,
            authorize=access,
            auto_audit=False,
        )

    def close_rift(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            self.game.unpaused(c)
            canon = load_state(c, self.store.campaign_id)
            portal = next((x for x in canon.void_rifts if x.id == identity and x.open), None)
            if (
                portal is None
                or canon.revision != expected
                or rules.controller(canon, portal.owner) != viewer.user_id
            ):
                raise WorkflowError(
                    "Only the actual Harpy who opened this Rift chooses its closure."
                )
            event = str(uuid4())
            canon.void_rifts = [
                x.model_copy(update={"open": False, "closed_event": event})
                if x.id == identity
                else x
                for x in canon.void_rifts
            ]
            self.game.event(
                c, viewer.user_id, key, "m3.harpy_rift_closed", canon, event_id=event, rift=identity
            )
            return dict(id=identity, closed=True)

        return self.store._write(
            viewer,
            key,
            "m3.harpy_rift_closed",
            dict(id=identity, expected=expected),
            operation,
            auto_audit=False,
        )
