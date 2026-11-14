"""Actual battle effect ports; canonical staging precedes, SQL work follows the real event."""

import hashlib
import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_battle as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_battle_state import Context, Declaration, Defense, Required
from girlframe.engine.m3_choices import CORE_RETALIATION
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.engine.m3_fuel_shortage import LossSelection
    from girlframe.engine.m3_handler_play_state import HandlerPlay
    from girlframe.services.m2_game import GameService


def _cast(game: "GameService", c: Connection, state: GameState, channel: int) -> SceneCast:
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    return CastService(ActorService(MissionService(game.store)))._current(c, state, channel)[0]


def _visible(state: GameState, ref: ActorRef, human: int) -> bool:
    if ref.kind in ("pilot", "handler"):
        return True
    harpy = next((x for x in state.harpy_states if x.id == ref.entity), None)
    if harpy is not None:
        return harpy.controller == human or harpy.revealed
    if state.world is None:
        return False
    rows = {
        "npc": state.world.npcs,
        "gorgon": state.world.gorgons,
        "external_pilot": state.world.pilots,
    }.get(ref.kind, ())
    actual = next((x for x in rows if x.id == ref.entity), None)
    return actual is not None and (
        getattr(actual, "controller", state.handler) == human
        or bool(getattr(actual, "revealed", False))
    )


def _scene_judge(
    game: "GameService", c: Connection, state: GameState, cast: SceneCast
) -> tuple[ActorRef | None, int, str | None]:
    campaign_gm, _ = MedicalService(game.store)._handler(c)
    directors = [
        x
        for x in cast.roles
        if x.actor.kind == "npc"
        and state.world is not None
        and any(
            npc.id == x.actor.entity and npc.alive and "director" in npc.jobs
            for npc in state.world.npcs
        )
    ]
    if not directors and cast.adjudicator is None:
        return None, campaign_gm, None
    selected = next((x for x in directors if x.actor == cast.adjudicator), None)
    if selected is None:
        raise WorkflowError(
            "Select the actual present Director's scene adjudicator before declaring battle."
        )
    policy = game.store.policy.owner_m3_rulings
    if policy is None or policy.director_adjudicator != "explicit_cast_director":
        raise WorkflowError("Record the source-owned explicit Director adjudicator ruling first.")
    history = t.m2["m2_state_history"]
    rows = c.execute(
        sa.select(t.events.c.id, t.events.c.actor_id, t.events.c.payload_json, history.c.body_json)
        .join(history, history.c.event_id == t.events.c.id)
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.scene_cast_changed",
            t.events.c.actor_id == str(selected.controller),
        )
        .order_by(t.events.c.seq.desc())
    ).mappings()
    for row in rows:
        payload = json.loads(row["payload_json"])
        if payload.get("action") != "adjudicate" or payload.get("scene") != cast.id:
            continue
        original = GameState.model_validate_json(row["body_json"])
        proof = next((x for x in original.scene_casts if x.id == cast.id), None)
        if (
            proof is not None
            and proof.adjudicator == selected.actor
            and any(
                x.actor == selected.actor and x.controller == selected.controller
                for x in proof.roles
            )
        ):
            return selected.actor, selected.controller, str(row["id"])
    raise WorkflowError(
        "SOURCE_JUDGE_MISSING: recover the actual Director human's selected role event."
    )


def proved_judge(
    game: "GameService", c: Connection, action: dict[str, Any]
) -> tuple[ActorRef | None, int, str]:
    meta = action["data"].get("battle")
    if meta is None:
        raise WorkflowError("Recover the actual original battle adjudication scope.")
    state = load_state(c, game.store.campaign_id)
    fact = next(
        (
            x
            for x in reversed(state.facts)
            if x.get("kind") == "battle_context" and x.get("id") == meta["context"]
        ),
        None,
    )
    value = Context.model_validate_json(fact["body"]) if fact else None
    if value is None:
        raise WorkflowError("Recover the original source battle Context.")
    _context_proof(game, c, value)
    controller = value.judge_controller or value.adjudicator
    ref = value.judge_actor
    if (
        meta.get("handler") != controller
        or meta.get("judge_actor") != (ref.model_dump(mode="json") if ref else None)
        or meta.get("judge_source") != value.judge_source
        or meta.get("procedural_gm") != value.adjudicator
        or meta.get("appointment") != value.appointment
    ):
        raise WorkflowError(
            "The actual original scoped adjudicator cannot transfer to another role."
        )
    if ref is not None:
        row = c.execute(
            sa.select(t.events.c.actor_id, t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.judge_source,
            )
        ).first()
        if (
            row is None
            or row.actor_id != str(controller)
            or row.kind != "m3.scene_cast_changed"
            or json.loads(row.payload_json).get("action") != "adjudicate"
        ):
            raise WorkflowError("Prove the actual frozen Director adjudicator's source selection.")
    return ref, controller, value.appointment


def proved_ended_original(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    actor: ActorRef,
) -> bool:
    """Only the actual rolled original Pilot's proved ending, never a same-UID successor."""
    meta = action["data"].get("battle", {})
    if actor.kind != "pilot" or meta.get("actor") != actor.model_dump(mode="json"):
        return False
    archive = next((x for x in state.career_archives if x.actor == actor), None)
    if archive is None or not meta.get("roll_event") or not action["data"].get("receipt"):
        return False
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == meta["roll_event"],
        )
    )
    rolled = GameState.model_validate_json(raw) if raw else None
    original = rolled.sheets.get(actor.entity) if rolled else None
    actual = c.execute(
        sa.select(t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == meta["roll_event"]
        )
    ).first()
    if original is None or original.character_id != actor.incarnation or actual is None:
        return False
    payload = json.loads(actual.payload_json)
    if (
        payload.get("action_id") != action["id"]
        or payload.get("receipt_id") != action["data"]["receipt"]["id"]
    ):
        return False
    ended = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == archive.source_event,
        )
    )
    proof = GameState.model_validate_json(ended) if ended else None
    return proof is not None and archive in proof.career_archives


def _context_proof(game: "GameService", c: Connection, value: Context) -> None:
    if value.source_author is not None:
        from girlframe.services.m3_handler_advancements import _history
        from girlframe.services.m3_princess_sex import _direction

        direction = _direction(
            game, c, _history(c, game, value.proposed_event), value.source_work or ""
        )
        if (
            direction.author_controller != value.source_author
            or direction.actor != value.declaration.actor
            or direction.parent != value.source_action
            or direction.play != value.declaration.play
            or direction.target != value.declaration.target
        ):
            raise WorkflowError("Preserve the actual Princess declaration author and performer")
    for event, kind, human in (
        (value.proposed_event, "m3.battle_proposed", value.source_author or value.owner),
        (value.confirmed_event, "m3.battle_confirmed", value.adjudicator),
    ):
        row = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        ).first()
        if (
            row is None
            or row.kind != kind
            or row.actor_id != str(human)
            or json.loads(row.payload_json).get("context") != value.id
        ):
            raise WorkflowError(
                "SOURCE_BATTLE_MISSING: recover both actual original human source events."
            )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.confirmed_event,
        )
    )
    source = GameState.model_validate_json(raw) if raw else None
    if source is None or not any(
        x.get("kind") == "battle_context"
        and x.get("id") == value.id
        and x.get("body") == value.model_dump_json()
        for x in source.facts
    ):
        raise WorkflowError(
            "SOURCE_BATTLE_MISSING: recover the exact immutable confirmed declaration."
        )


def authorize(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    action: dict[str, Any] | None = None,
) -> None:
    Access(game.store).authorize(c, viewer, "plays", director_response=True)
    game.unpaused(c)
    if action is not None:
        meta = action["data"]["battle"]
        approval = game.store.policy.m3_approval
        if approval is None or meta["registry"] != approval.registry_sha256:
            raise WorkflowError("M3_POLICY_CHANGED: recover the original battle release approval.")
        human, appointment = MedicalService(game.store)._handler(c)
        if appointment != meta["appointment"] or human != meta["procedural_gm"]:
            raise WorkflowError("Recover this battle's actual original adjudicator appointment.")
        proved_judge(game, c, action)


def _required_battle_child(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    """Route only proven required performances; each service retains its own authority."""
    from girlframe.services.m3_ankou_feedback_sequences import prepare_child as ankou_child
    from girlframe.services.m3_changeling_effects import prepare_child as mental_child
    from girlframe.services.m3_princess_sex import child_source as princess_child
    from girlframe.services.m3_red_queen_support import prepare_child as court_child

    for source in (court_child, ankou_child, mental_child, princess_child):
        value = source(game, c, viewer, state, prepared, channel)
        if value is not None:
            return value
    return None


def prepare(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    scene: dict[str, Any],
    prepared: PlayInput,
) -> dict[str, Any]:
    authorize(game, c, viewer)
    easy_child = None
    required_child = (
        _required_battle_child(game, c, viewer, state, prepared, int(scene["channel_id"]))
        if prepared.source_work
        else None
    )
    if prepared.source_work:
        from girlframe.services.m3_easy_target import prepare_child

        easy_child = prepare_child(game, c, viewer, state, prepared, int(scene["channel_id"]))
    # A witnessed-affection child is independently proved, not a free-form
    # exception for unrelated source_work. Its actual combat declaration still
    # supplies every opening, asset, controller and stale-state guard below.
    bonded_child = None
    if prepared.source_work and prepared.play in ("all_out_assault", "go_for_the_core"):
        from girlframe.services.m3_bonded import child_source as bonded_source

        bonded_child = bonded_source(game, c, viewer, state, prepared, int(scene["channel_id"]))
    if (
        prepared.target is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or prepared.source_work
        and easy_child is None
        and required_child is None
        and bonded_child is None
        or prepared.witnessed
    ):
        raise WorkflowError(
            "Battle uses its actual declared actors, not an unrelated order or downtime source."
        )
    context_id = getattr(prepared, "battle_context", None)
    raw = next(
        (
            x
            for x in reversed(state.facts)
            if x.get("kind") == "battle_context" and x.get("id") == context_id
        ),
        None,
    )
    if raw is None:
        raise WorkflowError("Confirm an actual opening, reach and owned Assets before rolling.")
    context = Context.model_validate_json(raw["body"])
    _context_proof(game, c, context)
    declaration = context.declaration
    if bonded_child is not None and (
        context.source_work is not None
        or declaration.actor.model_dump(mode="json") != bonded_child["actor"]
    ):
        raise WorkflowError(
            "Use this original witnessed-affection actor's independent battle declaration"
        )
    if required_child is not None and context.source_work != prepared.source_work:
        raise WorkflowError("Use the declaration bound to this actual original Court command")
    if prepared.parent != context.source_action:
        raise WorkflowError("Use this actual declaration's frozen original source parent.")
    if (
        context.state != "confirmed"
        or (context.source_author or context.owner) != viewer.user_id
        or context.scene != scene["id"]
    ):
        raise WorkflowError("Use your actual confirmed declaration in this original scene.")
    if any(
        x.get("kind") == "battle_context_used" and x.get("context") == context.id
        for x in state.facts
    ):
        raise WorkflowError("This source declaration has already started its one actual Play.")
    if prepared.play != declaration.play or prepared.target_actor != declaration.target:
        raise WorkflowError("Roll the actual declared Play against the original target.")
    if (
        prepared.attacking_asset != declaration.attacking_asset
        or prepared.target_asset != declaration.target_asset
    ):
        raise WorkflowError("Use the actual declared owned and opposing Assets.")
    bound = profiles(c, game.store.campaign_id)
    if context.defense is not None:
        BattleService(game.store)._defense(c, state, context, context.defense)
    acting = resolve(state, declaration.actor, bound, require_current_profile=False)
    target = resolve(state, declaration.target, bound, require_current_profile=False)
    if prepared.play == "all_out_assault" and declaration.actor.kind == "pilot":
        from girlframe.services.m3_learned_plays import (
            NO_ONE_BETTER,
            available,
            permanent_no_one_better,
        )

        if (
            permanent_no_one_better(state, declaration.actor)
            or available(game, c, state, declaration.actor, NO_ONE_BETTER) is not None
        ):
            registry = Access(game.store).registry
            if registry is None:
                raise WorkflowError("Approve the actual No One Better source before this Assault")
            registry.require_available("girl.casualty.no-one-better")
    if acting.offstage_source is not None or target.offstage_source is not None:
        raise WorkflowError(
            "Resolve the actual offstage travel before declaring a battlefield attack."
        )
    if prepared.piloting != bool(acting.piloting):
        raise WorkflowError("Use the original body's actual piloting context for this battle.")
    directed_author = bool(
        required_child is not None
        and context.source_author == viewer.user_id
        and context.owner == acting.controller
        and required_child.get("author") == viewer.user_id
        and required_child["actor"] == declaration.actor.model_dump(mode="json")
    )
    if (
        acting.controller != viewer.user_id
        and not directed_author
        or rules.resource_sha(state, declaration.actor, bound) != declaration.actor_sha256
    ):
        raise WorkflowError("STALE_BATTLE: the original actor or resources changed.")
    if rules.resource_sha(state, declaration.target, bound) != declaration.target_sha256:
        raise WorkflowError("STALE_BATTLE: the original target or resources changed.")
    cast = _cast(game, c, state, int(scene["channel_id"]))
    if (
        cast is None
        or cast.revision != context.cast_revision
        or not all(
            any(x.actor == ref for x in cast.roles)
            for ref in (declaration.actor, declaration.target)
        )
    ):
        raise WorkflowError("Recover the actual original battle cast.")
    strike = rules.owned_asset(
        state,
        declaration.actor,
        declaration.attacking_asset,
        bound,
        attacking=True,
        allow_damaged=declaration.play == "go_for_the_core",
    )
    if strike.damaged and not context.core_capability_confirmed:
        raise WorkflowError(
            "The damaged Asset's decisive-strike capability "
            "needs pre-roll Conversation confirmation."
        )
    if declaration.target_asset is not None:
        rules.owned_asset(state, declaration.target, declaration.target_asset, bound)
        if declaration.target.kind == "pilot" and target.inside_frame is None:
            raise WorkflowError(
                "Record the attacked original Girl's actual cockpit occupancy before rolling."
            )
    source = (
        rules.core_available(state, declaration.target, declaration.actor, bound)
        if prepared.play == "go_for_the_core"
        else None
    )
    if source != context.core_source:
        raise WorkflowError("STALE_CORE: recover this target's actual exposure facts.")
    if (
        acting.inside_frame is False
        and (
            declaration.target.kind == "gorgon"
            or target.inside_frame
            or declaration.target_asset is not None
            and next(x for x in target.assets if x.id == declaration.target_asset).family == "frame"
        )
        and not context.outside_permission
    ):
        raise WorkflowError("The Conversation must establish this actual outside-Frame attack.")
    for body, outside in (
        (acting, context.actor_outside_frame),
        (target, context.target_outside_frame),
    ):
        if body.ref.kind == "external_pilot" and rules.category(state, body.ref) != "harpy":
            raise WorkflowError(
                "UNSUPPORTED_RULE: support actual external Pilot Defeat/resources "
                "before this battle can roll."
            )
        if body.rules == "handler_girl" and outside is not True:
            raise WorkflowError(
                "Record this actual HandlerGirl body outside a Frame before combat; "
                "cockpit custody needs its actual physical port."
            )
    handler, appointment = MedicalService(game.store)._handler(c)
    if handler != context.adjudicator or appointment != context.appointment:
        raise WorkflowError("Recover the original actual human adjudicator.")
    assert game.store.policy.m3_approval is not None
    judge, judge_controller, judge_source = _scene_judge(game, c, state, cast)
    if (
        judge != context.judge_actor
        or judge_controller != context.judge_controller
        or judge_source != context.judge_source
    ):
        raise WorkflowError("STALE_JUDGE: recover the actual selected scene adjudicator.")
    from girlframe.services.m3_enforcer_firepower import prepare_firepower

    return dict(
        firepower=prepare_firepower(game, c, state, declaration.actor, cast, prepared),
        actor=declaration.actor.model_dump(mode="json"),
        target=declaration.target.model_dump(mode="json"),
        attacking_asset=declaration.attacking_asset,
        target_asset=declaration.target_asset,
        context=context.id,
        registry=game.store.policy.m3_approval.registry_sha256,
        handler=judge_controller,
        procedural_gm=handler,
        judge_actor=judge.model_dump(mode="json") if judge else None,
        judge_source=judge_source,
        cast_sha256=fingerprint(cast),
        appointment=appointment,
        target_controller=target.controller,
        actor_controller=acting.controller,
        table=sorted(
            {x.controller for x in cast.roles} | ({cast.facilitator} if cast.facilitator else set())
        ),
        target_category=rules.category(state, declaration.target),
        modifier=-len(rules.intact_assets(state, declaration.target, bound)) if source else 0,
        indirect=context.indirect,
        steps=[],
        votes={},
        source_core=source,
        followups=[],
        state="initial",
        defense=context.defense.model_dump(mode="json") if context.defense else None,
        dormant_awakened=context.dormant_awakened,
        dormant_close=context.dormant_close,
        occupancy={
            ref.token: False
            for ref, outside in (
                (declaration.actor, context.actor_outside_frame),
                (declaration.target, context.target_outside_frame),
            )
            if outside is True
        },
    )


def modifier(
    state: GameState, action: dict[str, Any], bindings: tuple[ProfileBinding, ...] = ()
) -> int:
    if action["data"].get("ankou_feedback") and action["data"]["play"] == "go_for_the_core":
        # The original declaration remains immutable. Only pre_roll's proved
        # Feedback/reprisal changes may have advanced these actual resources.
        _, target = _refs(action)
        return -len(rules.intact_assets(state, target, bindings))
    return int(action["data"]["battle"]["modifier"])


def feedback_source_binding(meta: dict[str, Any]) -> str:
    """Freeze the real initial battle inputs, not later result bookkeeping."""
    fields = (
        "firepower",
        "actor",
        "target",
        "attacking_asset",
        "target_asset",
        "context",
        "registry",
        "handler",
        "procedural_gm",
        "judge_actor",
        "judge_source",
        "cast_sha256",
        "appointment",
        "target_controller",
        "actor_controller",
        "table",
        "target_category",
        "modifier",
        "indirect",
        "source_core",
        "defense",
        "dormant_awakened",
        "dormant_close",
        "occupancy",
    )
    return hashlib.sha256(
        json.dumps({key: meta[key] for key in fields}, sort_keys=True).encode()
    ).hexdigest()


def pre_roll(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    *,
    commit: bool = True,
) -> None:
    meta = action["data"]["battle"]
    fact = next(
        (
            x
            for x in reversed(state.facts)
            if x.get("kind") == "battle_context" and x.get("id") == meta["context"]
        ),
        None,
    )
    if fact is None:
        raise WorkflowError("Recover the actual original battle declaration.")
    context = Context.model_validate_json(fact["body"])
    _context_proof(game, c, context)
    if context.defense is not None:
        BattleService(game.store)._defense(c, state, context, context.defense)
    if any(
        x.get("kind") == "battle_context_used" and x.get("context") == context.id
        for x in state.facts
    ):
        raise WorkflowError("This declaration already rolled its actual dice.")
    bound = profiles(c, game.store.campaign_id)
    expected = None
    if action["data"].get("ankou_feedback"):
        from girlframe.services.m3_ankou_feedback import engage_history, prove
        from girlframe.services.m3_disposable_psyche import _before

        feedback = prove(game, c, state, action["data"]["ankou_feedback"])
        cast = _cast(game, c, state, int(action["channel_id"]))
        if (
            feedback.battle_source != feedback_source_binding(meta)
            or feedback.battle_source is None
            or feedback.phase != "resolved"
            or feedback.resolved_event is None
            or feedback.actor != context.declaration.actor
            or context.declaration.play not in ("all_out_assault", "go_for_the_core")
            or context.declaration.play != feedback.prepared.play
            or context.source_action is not None
            or cast != feedback.cast
            or fingerprint(cast) != meta["cast_sha256"]
            or cast.revision != context.cast_revision
        ):
            attack = "Core" if feedback.prepared.play == "go_for_the_core" else "Assault"
            raise WorkflowError(f"Preserve the resolved original {attack} Feedback and scene cast")
        original = _before(game, c, feedback.mark_event)
        for ref, old_sha in (
            (context.declaration.actor, context.declaration.actor_sha256),
            (context.declaration.target, context.declaration.target_sha256),
        ):
            if rules.resource_sha(original, ref, bound) != old_sha:
                raise WorkflowError("Preserve the genuine pre-Feedback battle resources")
        expected = engage_history(
            game,
            c,
            feedback,
            original,
            (context.declaration.actor, context.declaration.target),
            battle=True,
        )
        # Feedback cannot replace the original attack or silently substitute a
        # weapon which its owner just tore off during the real interruption.
        strike = rules.owned_asset(
            state,
            context.declaration.actor,
            context.declaration.attacking_asset,
            bound,
            attacking=True,
            allow_damaged=context.declaration.play == "go_for_the_core",
        )
        if strike.damaged and not context.core_capability_confirmed:
            raise WorkflowError("Preserve the original damaged-Asset decisive-strike confirmation")
        if context.declaration.play == "go_for_the_core":
            for source_state in (original, state):
                if (
                    rules.core_available(
                        source_state, context.declaration.target, context.declaration.actor, bound
                    )
                    != context.core_source
                    or meta["source_core"] != context.core_source
                ):
                    raise WorkflowError("STALE_CORE: preserve the original Feedback-held exposure")
            if meta["modifier"] != -len(
                rules.intact_assets(original, context.declaration.target, bound)
            ):
                raise WorkflowError("Preserve the genuine initial Core Asset penalty")
        else:
            assert context.declaration.target_asset is not None
            rules.owned_asset(
                state, context.declaration.target, context.declaration.target_asset, bound
            )
    for ref, old_sha in (
        (context.declaration.actor, context.declaration.actor_sha256),
        (context.declaration.target, context.declaration.target_sha256),
    ):
        if expected is not None:
            old_sha = rules.resource_sha(expected, ref, bound)
        if action["data"].get("learned_no_one_better"):
            from girlframe.services.m3_learned_plays import triggered_resource_sha

            old_sha = triggered_resource_sha(game, c, state, action, ref, old_sha)
        if rules.resource_sha(state, ref, bound) != old_sha:
            raise WorkflowError("STALE_BATTLE: actual combat resources changed before dice.")
    from girlframe.engine.m3_budget_sabotage import matching as trapped_assets

    if trapped_assets(state, context.declaration.actor, {context.declaration.attacking_asset}):
        raise WorkflowError(
            "SOURCE_PORT_REQUIRED: resolve this battle Asset's sabotage before dice"
        )
    if commit:
        commit_declaration(state, action)


def commit_declaration(state: GameState, action: dict[str, Any]) -> None:
    """Consume the checked declaration only when this Play proceeds to actual dice."""
    meta = action["data"]["battle"]
    if any(
        x.get("kind") == "battle_context_used" and x.get("context") == meta["context"]
        for x in state.facts
    ):
        raise WorkflowError("This declaration already rolled its actual dice.")
    meta["roll_event"] = str(uuid4())
    state.facts.append(
        dict(
            kind="battle_context_used",
            context=meta["context"],
            action=action["id"],
            event=meta["roll_event"],
        )
    )


def _refs(action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    meta = action["data"]["battle"]
    return tuple(ActorRef.model_validate_json(json.dumps(meta[x])) for x in ("actor", "target"))  # type: ignore[return-value]


def results(
    game: "GameService", c: Connection, action: dict[str, Any], *, state: GameState | None = None
) -> None:
    from girlframe.services.m3_enforcer_firepower import results_firepower

    if results_firepower(game, c, action):
        return
    meta = action["data"]["battle"]
    level = action["data"]["result"]["tier"]
    learned_extra = False
    if action["data"].get("learned_no_one_better"):
        from girlframe.services.m3_learned_plays import resolve_no_one_better

        state = state if state is not None else load_state(c, game.store.campaign_id)
        learned_extra = resolve_no_one_better(
            game, c, state, action, action["data"].get("response_event", "")
        )
    if (
        action["data"]["play"] == "all_out_assault"
        and level == "high"
        and not meta.get("extra_started")
    ):
        from girlframe.services.m3_learned_plays import permanent_no_one_better

        state = state if state is not None else load_state(c, game.store.campaign_id)
        actor, _ = _refs(action)
        if permanent_no_one_better(state, actor) or learned_extra:
            from girlframe.services.m3_engage import start_assault_extra

            meta["extra_source"] = "girl.casualty.no-one-better"
            start_assault_extra(game, c, action)
            return
    if action["data"]["play"] == "go_for_the_core" and level == "high":
        state = load_state(c, game.store.campaign_id)
        _, target = _refs(action)
        meta["fixed_assets"] = [
            x.id for x in rules.intact_assets(state, target, profiles(c, game.store.campaign_id))
        ]
    if action["data"]["play"] == "all_out_assault":
        if level == "low":
            game.request(
                c,
                action,
                meta["target_controller"],
                "battle_low_damage",
                dict(target=meta["actor"], actor=meta["actor"]),
            )
        else:
            for human in meta["table"]:
                game.request(c, action, human, "battle_assault_table", dict(target=meta["target"]))
    elif level == "mid":
        meta["fixed_due"] = "death"
    else:
        game.request(
            c,
            action,
            meta["target_controller"],
            "battle_counter",
            dict(actor=meta["target"], attacker=meta["actor"], maximum=2 if level == "low" else 1),
        )
    meta["state"] = "choices"


def damage_projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Source-owned consequence controls shared by actual combat/Engage consumers."""
    body = json.loads(request["body_json"])
    identity = body.get("work_id")
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or body.get("source_action") != action["id"]:
        raise WorkflowError("Recover the exact actual source-owned damage continuation.")
    saved = json.loads(row["body_json"])
    if saved.get("continuation") != request["id"] or saved.get("source_action") != action["id"]:
        raise WorkflowError("This consequence belongs to another original source Play.")
    return dict(
        kind=request["kind"],
        work_id=identity,
        owner=saved.get("owner"),
        requirement=saved.get("requirement"),
    )


def apply_damage_response(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    damage_projection(game, c, state, action, request)
    raise WorkflowError(
        "Open and complete this actual source-owned consequence; it cannot be acknowledged away."
    )


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    if request["kind"] in ("battle_collateral", "battle_quadrant_loss", "battle_aggressive_damage"):
        return damage_projection(game, c, state, action, request)
    meta = action["data"]["battle"]
    actor, target = _refs(action)
    bound = profiles(c, game.store.campaign_id)
    destination = (
        actor if request["kind"] in ("battle_low_damage", "battle_actor_damage") else target
    )
    detail: dict[str, Any] = dict(
        level=action["data"]["result"]["tier"],
        kind=request["kind"],
        assets=[dict(id=x.id, name=x.name) for x in rules.intact_assets(state, destination, bound)],
        options=list(CORE_RETALIATION)
        if request["kind"] == "battle_counter"
        else ["collateral_damage", "handler_play", "damage_actor_asset"]
        if request["kind"] == "battle_handler"
        else [],
        target=meta["target"],
        **{
            k: v
            for k, v in json.loads(request["body_json"]).items()
            if k in ("maximum", "work_id", "grant_id")
        },
    )
    if action["data"].get("learned_no_one_better"):
        from girlframe.services.m3_learned_plays import consumed_no_one_better

        detail["learned_rider"] = (
            "No One Better: spent once for this genuine high Assault; "
            "the learner's own Assets and ordinary Assault costs remain."
            if consumed_no_one_better(game, c, state, action)
            else "No One Better did not trigger on this receipt; the lesson remains unused."
        )
    if request["kind"] == "battle_target_damage":
        detail["assets"] = [x for x in detail["assets"] if x["id"] in meta.get("fixed_assets", [])]
    if request["kind"] == "battle_counter_play":
        if meta["target_category"] == "npc":
            from girlframe.engine.m3_battle_npc import NARRATIVE

            npc = (
                next(x for x in state.world.npcs if x.id == target.entity) if state.world else None
            )
            detail["own_plays"] = (
                [dict(id=job, label=NARRATIVE[job][0]) for job in npc.jobs if job in NARRATIVE]
                if npc
                else []
            )
        elif target.kind == "gorgon":
            gorgon = (
                next(x for x in state.world.gorgons if x.id == target.entity)
                if state.world
                else None
            )
            detail["own_plays"] = [
                dict(id="warp_escalate", label="Warp: escalate/change situation"),
                dict(id="warp_protect", label="Warp: grow flesh and protect Core"),
            ]
            if gorgon and any(x.damaged for x in gorgon.assets):
                detail["own_plays"].append(
                    dict(id="warp_evolve", label="Warp: evolve a real new Asset")
                )
        else:
            detail["own_plays"] = []
        detail["counter_actor"] = meta["target"]
        detail["counter_target"] = meta["actor"]
    return detail


def _strict(answer: ChoiceAnswer, allowed: set[str]) -> None:
    baseline = ChoiceAnswer()
    if any(
        getattr(answer, key) != getattr(baseline, key)
        for key in ChoiceAnswer.model_fields
        if key not in allowed
    ):
        raise WorkflowError("Supply only the actual current battle choice fields.")


def _damage(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorRef,
    asset: str | None,
    event: str,
    *,
    opponent: ActorRef,
    chooser: int,
    occurrence: str,
) -> None:
    changed, followups = damage_actor(
        game,
        c,
        state,
        target=target,
        asset_id=asset,
        source_action=action["id"],
        source_work=None,
        event=event,
        actor=opponent,
        chooser_controller=chooser,
        occurrence=occurrence,
        indirect=action["data"]["battle"]["indirect"],
    )
    _copy(state, changed)
    action["data"]["battle"]["followups"].extend(followups)


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.engine.m3_actor_bonds import make_helpless

    meta = action["data"]["battle"]
    actor, target = _refs(action)
    kind = request["kind"]
    event = action["data"]["response_event"]
    level = action["data"]["result"]["tier"]
    if kind == "battle_assault_table":
        _strict(answer, {"flag", "text"})
        if answer.flag is None or not answer.text.strip():
            raise WorkflowError("State your actual agreement or disagreement with vast advantage.")
        meta["votes"][request["actor_id"]] = dict(vast=answer.flag, account=answer.text)
        if len(meta["votes"]) == len(meta["table"]):
            if not all(x["vast"] for x in meta["votes"].values()):
                _damage(
                    game,
                    c,
                    state,
                    action,
                    target,
                    meta["target_asset"],
                    event,
                    opponent=actor,
                    chooser=meta["actor_controller"],
                    occurrence="assault",
                )
            meta["assault_applied"] = True
            if level == "high":
                game.request(
                    c, action, meta["handler"], "battle_handler", dict(actor=meta["actor"])
                )
        return
    if kind in ("battle_low_damage", "battle_actor_damage", "battle_target_damage"):
        _strict(answer, {"fields"})
        if set(answer.fields) != {"asset"}:
            raise WorkflowError("Choose the actual current undamaged Asset.")
        if kind == "battle_target_damage" and answer.fields["asset"] not in meta.get(
            "fixed_assets", []
        ):
            raise WorkflowError(
                "Pay this strike with an actual originally eligible Asset, not a later evolution."
            )
        affected, foe = (target, actor) if kind == "battle_target_damage" else (actor, target)
        chooser = meta["target_controller"] if affected == actor else meta["actor_controller"]
        _damage(
            game,
            c,
            state,
            action,
            affected,
            answer.fields["asset"],
            event,
            opponent=foe,
            chooser=chooser,
            occurrence=request["id"],
        )
        if kind == "battle_low_damage":
            _forced_handler(game, c, state, action, request, event, "low")
        if kind == "battle_target_damage":
            meta["fixed_paid"] = event
        return
    if kind == "battle_handler":
        _strict(answer, {"options", "text"})
        allowed = {"collateral_damage", "handler_play", "damage_actor_asset"}
        if not 1 <= len(answer.options) <= 2 or not set(answer.options) <= allowed:
            raise WorkflowError("The actual Handler chooses one or two printed consequences.")
        if "damage_actor_asset" in answer.options:
            game.request(
                c,
                action,
                meta["actor_controller"],
                "battle_actor_damage",
                dict(target=meta["actor"], actor=meta["actor"]),
            )
        if "handler_play" in answer.options:
            _forced_handler(game, c, state, action, request, event, "high")
        if "collateral_damage" in answer.options:
            if not answer.text.strip():
                raise WorkflowError("Describe the actual reasonably destroyed collateral.")
            from girlframe.engine.m3_collateral import Source
            from girlframe.engine.m3_handler_consequences import active_handler

            collateral = Source(
                id=str(uuid5(NAMESPACE_URL, request["id"] + ":collateral")),
                action=action["id"],
                choice=request["id"],
                event=event,
                actor=actor,
                actor_controller=meta["actor_controller"],
                judge=meta["handler"],
                appointment=meta["appointment"],
                handler=active_handler(state),
            )
            state.facts.append(
                dict(
                    kind="collateral_stage",
                    id=collateral.id,
                    event=event,
                    body=collateral.model_dump_json(),
                )
            )
        return
    if kind == "battle_counter":
        _strict(answer, {"options", "flag", "text"})
        maximum = 2 if level == "low" else 1
        if not answer.options and answer.flag is not False:
            raise WorkflowError(
                "Explicitly decline the optional counter or choose printed effects."
            )
        if len(answer.options) > maximum or not set(answer.options) <= set(CORE_RETALIATION):
            raise WorkflowError("Choose only this actual target's permitted distinct counters.")
        meta["counters"] = list(answer.options)
        if "damage_actor_asset" in answer.options:
            game.request(
                c,
                action,
                meta["target_controller"],
                "battle_actor_damage",
                dict(target=meta["actor"], actor=meta["actor"]),
            )
        if "actor_helpless" in answer.options:
            if actor.kind == "handler":
                raise WorkflowError("Use the actual Handler Helpless replacement source port.")
            _copy(state, make_helpless(state, actor, target, event))
        if "target_dies_with_handler_play" in answer.options:
            from girlframe.services.m3_handler_plays import request_handler_play

            changed, grant = request_handler_play(
                game,
                c,
                action["id"],
                request["id"],
                "go_for_the_core." + level,
                target,
                meta["target_controller"],
                actor,
                event,
                state=state,
                final_original=True,
            )
            _copy(state, changed)
            game.request(
                c, action, meta["target_controller"], "battle_handler_play", dict(grant_id=grant)
            )
            meta["die_anyway"] = True
        if "make_play_against_actor" in answer.options:
            actual_target = resolve(
                state, target, profiles(c, game.store.campaign_id), require_current_profile=False
            )
            if actual_target.rules in ("handler", "director"):
                from girlframe.services.m3_handler_plays import request_handler_play

                changed, grant = request_handler_play(
                    game,
                    c,
                    action["id"],
                    request["id"],
                    "go_for_the_core." + level,
                    target,
                    meta["target_controller"],
                    actor,
                    event,
                    state=state,
                )
                _copy(state, changed)
                game.request(
                    c,
                    action,
                    meta["target_controller"],
                    "battle_handler_play",
                    dict(grant_id=grant),
                )
            else:
                game.request(
                    c,
                    action,
                    meta["target_controller"],
                    "battle_counter_play",
                    dict(actor=meta["target"], attacker=meta["actor"]),
                )
        if level == "high" and meta["target_category"] != "npc" and not meta.get("die_anyway"):
            if meta.get("fixed_assets"):
                meta["fixed_due"] = "damage"
            else:
                meta["die_anyway"] = True
        if (
            meta["target_category"] == "npc" and (level == "high" or not meta.get("defense"))
        ) or meta.get("die_anyway"):
            meta["fixed_due"] = "death"
        return
    if kind == "battle_counter_play" and meta["target_category"] == "npc":
        from girlframe.engine.m3_battle_npc import NARRATIVE

        _strict(answer, {"fields", "text"})
        if set(answer.fields) != {"play"} or not answer.text.strip():
            raise WorkflowError(
                "Choose the NPC's actual job-defined Play and perform it against the attacker."
            )
        assert state.world is not None
        npc = next(x for x in state.world.npcs if x.id == target.entity and x.alive)
        job = answer.fields["play"]
        if job not in npc.jobs or job not in NARRATIVE:
            raise WorkflowError("This actual NPC does not own the selected source Play.")
        label, pdf = NARRATIVE[job]
        state.facts.append(
            dict(
                kind="performed_npc_play",
                actor=target.model_dump_json(),
                target=actor.model_dump_json(),
                job=job,
                play=label,
                source_pdf=str(pdf),
                action=action["id"],
                source_choice=request["id"],
                event=event,
                account=answer.text,
            )
        )
        return
    if kind == "battle_counter_play" and target.kind == "gorgon":
        _strict(answer, {"fields", "text"})
        if not answer.text.strip() or "play" not in answer.fields:
            raise WorkflowError(
                "Perform the actual Gorgon's own printed Warp against the attacker."
            )
        assert state.world is not None
        gorgon = next(x for x in state.world.gorgons if x.id == target.entity and x.alive)
        option = answer.fields["play"]
        if not gorgon.exposed:
            raise WorkflowError("Warp requires this actual Gorgon's exposed Core.")
        if option == "warp_evolve":
            from girlframe.engine.m3_world_state import Asset

            if set(answer.fields) != {"play", "name", "description"} or not any(
                x.damaged for x in gorgon.assets
            ):
                raise WorkflowError(
                    "Evolve one actual new Asset only while original Assets are damaged."
                )
            new = Asset(
                id=str(uuid4()),
                name=answer.fields["name"],
                description=answer.fields["description"],
                family="gorgon",
            )
            gorgon = gorgon.model_copy(update={"assets": gorgon.assets + (new,)})
        elif option == "warp_protect":
            if set(answer.fields) != {"play"} or level not in ("high", "low"):
                raise WorkflowError(
                    "Protect this actual Core only after the real failed Core strike."
                )
            gorgon = gorgon.model_copy(update={"exposed": False, "core_strike_failed": False})
        elif option == "warp_escalate":
            if set(answer.fields) != {"play"}:
                raise WorkflowError("Describe only the actual changed situation.")
        else:
            raise WorkflowError("Select a real owned Gorgon counter Play.")
        state.world = state.world.model_copy(
            update={
                "gorgons": tuple(gorgon if x.id == gorgon.id else x for x in state.world.gorgons)
            }
        )
        state.facts.append(
            dict(
                kind="performed_gorgon_warp",
                actor=target.model_dump_json(),
                target=actor.model_dump_json(),
                play=option,
                source_pdf="162",
                action=action["id"],
                source_choice=request["id"],
                event=event,
                account=answer.text,
            )
        )
        return
    raise WorkflowError("Resolve this battle's actual source-owned effect or child Play.")


def _forced_handler(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    event: str,
    level: str,
) -> None:
    from girlframe.services.m3_handler_plays import request_forced_handler_play

    actor, _ = _refs(action)
    changed, grant = request_forced_handler_play(
        game,
        c,
        state,
        source_action=action["id"],
        source_choice=request["id"],
        clause="all_out_assault." + level,
        chooser_controller=action["data"]["battle"]["handler"],
        victim_actor=actor,
        event=event,
        action=action,
    )
    _copy(state, changed)
    game.request(
        c, action, action["data"]["battle"]["handler"], "battle_handler_play", dict(grant_id=grant)
    )


def _close_ended_actor_damage(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> str:
    state = load_state(c, game.store.campaign_id)
    actor, _ = _refs(action)
    if not proved_ended_original(game, c, state, action, actor):
        return event
    for request in game.pending(c, action["id"]):
        if request["kind"] not in ("battle_low_damage", "battle_actor_damage"):
            continue
        body = json.loads(request["body_json"])
        if body.get("actor") != actor.model_dump(mode="json"):
            raise WorkflowError("Recover the exact unavailable original body's damage source.")
        source = str(uuid4())
        choices = t.m2["m2_choices"]
        c.execute(
            choices.update()
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == request["id"],
                choices.c.state == "pending",
            )
            .values(state="completed_original_ended", revision=choices.c.revision + 1)
        )
        if request["kind"] == "battle_low_damage":
            _forced_handler(game, c, state, action, request, source, "low")
        state.facts.append(
            dict(
                kind="battle_original_damage_unavailable",
                action=action["id"],
                actor=actor.model_dump_json(),
                source_choice=request["id"],
                event=source,
            )
        )
        game.save_action(c, action)
        human = (
            viewer.user_id
            if viewer is not None
            else c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            )
        )
        if human is None:
            raise WorkflowError("Recover the real source command for original-body closure.")
        index = c.scalar(
            sa.select(sa.func.max(t.events.c.event_index)).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
            )
        )
        game.event(
            c,
            human,
            key,
            "m3.battle_original_damage_unavailable",
            state,
            event_id=source,
            event_index=index + 1 if index is not None else 0,
            source_event=event,
            source_action=action["id"],
            source_choice=request["id"],
        )
        event = source
    return event


def synchronize(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    if action["data"].get("ankou_feedback") and not action["data"].get("receipt"):
        # Feedback owns its unrolled refusal/death or exact ready-to-roll state.
        # A completed purpose is not a completed attack or a battle result.
        return
    if (
        action["data"].get("result")
        and action["data"]["battle"].get("dormant_awakened")
        and not action["data"]["battle"].get("dormant_staged")
    ):
        event = _dormant_awakening(game, c, action, event, viewer, key)
    from girlframe.services.m3_collateral import materialize
    from girlframe.services.m3_collateral import synchronize as synchronize_collateral

    materialize(game, c, action, event)
    synchronize_damage(game, c, event)
    synchronize_collateral(game, c, action, event)
    event = _close_ended_actor_damage(game, c, action, event, viewer, key)
    state = load_state(c, game.store.campaign_id)
    meta = action["data"]["battle"]
    if not game.pending(c, action["id"]) and meta.get("fixed_due") and not meta.get("fixed_paid"):
        _, target = _refs(action)
        ended = rules.original_ended(state, target)
        if ended:
            meta["fixed_paid"] = "original_body_already_ended"
        elif meta["fixed_due"] == "damage" and not meta.get("fixed_started"):
            eligible = [
                x
                for x in rules.intact_assets(state, target, profiles(c, game.store.campaign_id))
                if x.id in meta["fixed_assets"]
            ]
            if eligible:
                game.request(
                    c,
                    action,
                    meta["target_controller"],
                    "battle_target_damage",
                    dict(target=meta["target"]),
                )
                meta["fixed_started"] = True
                game.save_action(c, action)
                return
            meta["fatal_pending"] = True
        elif meta["fixed_due"] == "death":
            meta["fatal_pending"] = True
    if not game.pending(c, action["id"]) and action["data"]["battle"].get("fatal_pending"):
        _apply_fatal(game, c, state, action, event, viewer, key)
        state = load_state(c, game.store.campaign_id)
    for archive in state.career_archives:
        if archive.source_event == event:
            from girlframe.services.m3_careers import synchronize_end

            synchronize_end(
                c, game, archive, exclude_work=tuple(action["data"]["battle"]["followups"])
            )
    from girlframe.services.m3_engage import ensure_assault_extra

    if not ensure_assault_extra(game, c, state, action, event, viewer, key):
        game.save_action(c, action)
        return
    if not game.pending(c, action["id"]):
        from girlframe.services.m2_choices import ChoiceEngine

        if action["data"].get("actor_basic"):
            from girlframe.services.m3_actor_plays import ActorPlayService

            ActorPlayService(game).finish(c, state, action)
        else:
            ChoiceEngine(game).finish(c, state, action)
        game.save_action(c, action)
        if action["state"] == "complete" and action["data"].get("princess_child"):
            from girlframe.services.m3_princess_performer import complete_battle

            complete_battle(game, c, action, event)
        if action["data"].get("battle_counter_source"):
            complete_counter_play(game, c, action, event, viewer, key)
        if action["state"] == "complete" and action["data"].get("gorgon_counter_source"):
            from girlframe.services.m3_gorgon_play import complete_response

            complete_response(game, c, action, event, viewer, key)


def _dormant_awakening(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    source_event: str,
    viewer: GuildViewer | None,
    key: str,
) -> str:
    meta = action["data"]["battle"]
    actor, gorgon = _refs(action)
    state = load_state(c, game.store.campaign_id)
    if any(
        x.get("kind") == "dormant_awakening" and x.get("gorgon") == gorgon.entity
        for x in state.facts
    ):
        raise WorkflowError("This actual Gorgon has already been forced out of dormancy.")
    if state.world is None or not any(
        x.id == gorgon.entity and x.gorgon_class == "dormant" for x in state.world.gorgons
    ):
        raise WorkflowError("Recover the original actual Dormant Gorgon.")
    event = str(uuid4())
    identity = str(
        uuid5(NAMESPACE_URL, "girlframe:battle-dormant:" + action["id"] + ":" + gorgon.token)
    )
    required = Required(
        kind="dormant_void",
        target=actor,
        opponent=gorgon,
        source_pdf=165,
        details=dict(
            gorgon=gorgon.entity,
            close="true" if meta["dormant_close"] else "false",
            awakened_event=event,
        ),
    )
    state.facts.append(
        dict(
            kind="dormant_awakening",
            gorgon=gorgon.entity,
            actor=actor.model_dump_json(),
            source_action=action["id"],
            source_choice="",
            event=event,
            attack_event=source_event,
        )
    )
    state.facts.append(
        dict(
            kind="battle_damage_stage",
            id=identity,
            stamp=identity,
            event=event,
            source_action=action["id"],
            source_work="",
            requirement=required.model_dump_json(),
            chooser=str(meta["actor_controller"]),
        )
    )
    meta["followups"].append(identity)
    meta["dormant_staged"] = identity
    actual = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == source_event
        )
    )
    if actual is None:
        raise WorkflowError("Recover the actual attack event before its Dormant consequence.")
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    game.event(
        c,
        viewer.user_id if viewer else actual,
        key,
        "m3.battle_dormant_awakened",
        state,
        event_id=event,
        event_index=(index + 1 if index is not None else 0),
        source_event=source_event,
        action_id=action["id"],
        work_id=identity,
    )
    game.save_action(c, action)
    return event


def _apply_fatal(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    source_event: str,
    viewer: GuildViewer | None,
    key: str,
    *,
    allow_sprite: bool = True,
) -> None:
    """A printed deterministic death is an effect, never a fabricated Handler-owned answer."""
    from girlframe.engine.m3_physical import interrupt_journeys

    meta = action["data"]["battle"]
    _, target = _refs(action)
    if meta.get("fatal_event"):
        return
    if rules.original_ended(state, target):
        meta["fatal_pending"] = False
        meta["already_ended_source_state"] = source_event
        game.save_action(c, action)
        return
    ended = next((x for x in state.career_archives if x.actor == target), None)
    ended_handler = next((x for x in state.handler_archives if x.actor == target), None)
    if ended is not None or ended_handler is not None:
        actual_ending = (
            ended.source_event
            if ended is not None
            else ended_handler.source_event
            if ended_handler
            else ""
        )
        meta["fatal_pending"] = False
        meta["already_ended_original"] = actual_ending
        game.save_action(c, action)
        return
    event = str(uuid4())
    if allow_sprite:
        from girlframe.services.m3_sprite import defer_fatal

        actor, _ = _refs(action)
        deferred, interceptions = defer_fatal(
            game, c, state, action, target, event, opponent=actor, chooser=meta["actor_controller"]
        )
        if interceptions:
            meta.update(
                fatal_pending=False, fixed_paid="awaiting_sprite", fatal_sprite=interceptions[0]
            )
            meta["followups"].extend(interceptions)
            game.save_action(c, action)
            human = c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == source_event
                )
            )
            if human is None:
                raise WorkflowError("Recover the actual source command for the Core interception.")
            index = c.scalar(
                sa.select(sa.func.max(t.events.c.event_index)).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
                )
            )
            game.event(
                c,
                viewer.user_id if viewer else human,
                key,
                "m3.core_strike_awaits_sprite",
                deferred,
                event_id=event,
                event_index=index + 1 if index is not None else 0,
                source_event=source_event,
                source_action=action["id"],
            )
            synchronize_damage(game, c, event)
            return
    account = "Actual decisive Core strike, " + action["data"]["result"]["tier"] + " result"
    if target.kind == "pilot":
        from girlframe.engine.m3_careers import end

        profile = c.execute(
            sa.select(t.characters.c.id, t.characters.c.revision).where(
                t.characters.c.campaign_id == game.store.campaign_id,
                t.characters.c.user_id == target.entity,
            )
        ).first()
        if profile is None:
            raise WorkflowError("Recover the original dying character's actual profile source.")
        state = end(
            state,
            target,
            reason="death",
            source_event=event,
            account=account,
            archive_id=str(uuid4()),
            profile_id=profile.id,
            profile_revision=profile.revision,
        )
    elif target.kind == "handler":
        from girlframe.services.m3_handler_consequences import force_end_handler

        state = force_end_handler(
            game,
            c,
            state,
            target,
            source_action=action["id"],
            source_choice=None,
            clause="go_for_the_core." + action["data"]["result"]["tier"],
            event=event,
            account=account,
        )
    elif target.kind == "npc" and meta["target_category"] == "handler":
        from girlframe.engine.m3_battle_director import die
        from girlframe.services.m3_battle_director import bind_legacy_context_bodies

        state = die(bind_legacy_context_bodies(game, c, state), target, event, account)
    else:
        state = interrupt_journeys(state, target, event, account)
        state = rules.end_actor_casts(state, target, event)
        if target.kind == "external_pilot" and rules.category(state, target) == "harpy":
            from girlframe.engine.m3_harpy_defeat import die as die_harpy

            state = die_harpy(state, target, event)
        elif state.world is not None:
            if target.kind == "gorgon":
                # This exact original Core was exposed when the strike was made.
                # A last counter may close it but cannot undo its frozen fatal hit.
                if not meta.get("source_core"):
                    raise WorkflowError("Recover the actual original exposed Core strike source.")
                state.world = state.world.model_copy(
                    update={
                        "gorgons": tuple(
                            x.model_copy(update={"alive": False}) if x.id == target.entity else x
                            for x in state.world.gorgons
                        )
                    }
                )
            elif target.kind == "npc":
                state.world = state.world.model_copy(
                    update={
                        "npcs": tuple(
                            x.model_copy(update={"alive": False}) if x.id == target.entity else x
                            for x in state.world.npcs
                        )
                    }
                )
            else:
                state.world = state.world.model_copy(
                    update={
                        "pilots": tuple(
                            x.model_copy(update={"alive": False}) if x.id == target.entity else x
                            for x in state.world.pilots
                        )
                    }
                )
    from girlframe.engine.m3_leviathan_obsession import release_dead_sources

    state = release_dead_sources(state, event)
    meta["fatal_event"] = event
    meta["fatal_pending"] = False
    game.save_action(c, action)
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    source_actor = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == source_event
        )
    )
    if source_actor is None:
        raise WorkflowError("Recover the actual source command principal for deterministic death.")
    game.event(
        c,
        viewer.user_id if viewer is not None else source_actor,
        key,
        "m3.battle_actual_death",
        state,
        event_id=event,
        event_index=(index + 1 if index is not None else 0),
        source_event=source_event,
        action_id=action["id"],
        target=target.model_dump(mode="json"),
    )
    synchronize_casts(game, c, event)
    if target.kind == "gorgon":
        from girlframe.services.m3_gorgon_dormant import synchronize_endings as end_gorgon_costs

        end_gorgon_costs(game, c, event, viewer, key)
    if target.kind == "external_pilot" and rules.category(state, target) == "harpy":
        from girlframe.services.m3_harpy_rest import synchronize_endings

        synchronize_endings(game, c, event)
    if target.kind == "npc" and meta["target_category"] == "handler":
        from girlframe.services.m3_battle_director import create_replacements
        from girlframe.services.m3_handler_void import (
            synchronize_endings as synchronize_handler_void,
        )

        synchronize_handler_void(game, c, event, viewer, key)
        create_replacements(game, c, event)
    if target.kind == "pilot":
        from girlframe.services.m3_careers import synchronize_end

        synchronize_end(c, game, state.career_archives[-1], exclude_work=tuple(meta["followups"]))
    if target.kind == "handler":
        from girlframe.services.m3_handler_consequences import end_body_reviews, finish_callback

        for archive in state.handler_archives:
            if archive.source_event == event:
                end_body_reviews(game, c, archive)
        for record in state.handler_consequences:
            if record.effect_event == event:
                finish_callback(game, c, record, event, viewer, key)


def synchronize_casts(game: "GameService", c: Connection, event: str) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    source = GameState.model_validate_json(raw) if raw else None
    if source is None or not any(
        x.get("kind") == "battle_actor_cast_ended" and x.get("event") == event for x in source.facts
    ):
        return
    scenes = t.m2["m2_scenes"]
    for cast in source.scene_casts:
        people = sorted(
            {x.controller for x in cast.roles} | ({cast.facilitator} if cast.facilitator else set())
        )
        c.execute(
            scenes.update()
            .where(scenes.c.campaign_id == game.store.campaign_id, scenes.c.id == cast.id)
            .values(participants_json=json.dumps(people), revision=scenes.c.revision + 1)
        )


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def damage_actor(
    game: "GameService",
    c: Connection,
    state: GameState,
    *,
    target: ActorRef,
    asset_id: str | None,
    source_action: str | None,
    source_work: str | None,
    event: str,
    actor: ActorRef | None = None,
    opponent: ActorRef | None = None,
    chooser_controller: int | None = None,
    occurrence: str = "damage",
    indirect: bool = False,
    physical_blow: bool | None = None,
    allow_sprite: bool = True,
) -> tuple[GameState, tuple[str, ...]]:
    """Trusted consumer port; exact source grant/action, no fictitious GM body or audit event."""
    if not source_action and not source_work:
        raise WorkflowError("Damage needs its actual source Play or source-owned effect grant.")
    from girlframe.services.m3_wyvern_combat import require_damage_allowed

    require_damage_allowed(game, c, state, target)
    bound = profiles(c, game.store.campaign_id)
    target_view = resolve(state, target, bound, require_current_profile=False)
    if any(x.id == asset_id and x.family == "girl" for x in target_view.assets):
        from girlframe.engine.m3_am import require_harm

        require_harm(state, actor, target)
    from girlframe.engine.m3_ankou import Touch as AnkouTouch
    from girlframe.engine.m3_ankou import records as ankou_records
    from girlframe.engine.m3_changeling import Fingers as ChangelingFingers
    from girlframe.engine.m3_changeling import records as changeling_records
    from girlframe.engine.m3_easy_target import NpcHurt
    from girlframe.engine.m3_easy_target import records as easy_target_records
    from girlframe.engine.m3_wyvern import RousedUse
    from girlframe.engine.m3_wyvern import records as wyvern_records

    grant = next((x for x in state.handler_plays if x.id == source_work), None)
    if grant is not None:
        from girlframe.services.m3_handler_plays import validate_damage_source

        validate_damage_source(c, game, state, grant.id, target, actor, chooser_controller, event)
    elif source_work and source_work.startswith("a-bomb-drop:"):
        from girlframe.services.m3_a_bomb import prove_drop

        blast = prove_drop(game, c, state, source_work)
        resource = next((x for x in blast.resources if x.actor == target and x.event is None), None)
        if (
            resource is None
            or asset_id not in resource.assets
            or actor != blast.handler
            or chooser_controller != resource.controller
        ):
            raise WorkflowError("Only actual outstanding nuclear source damage uses this port")
    elif source_work and any(x.id == source_work for x in wyvern_records(state, RousedUse)):
        from girlframe.services.m3_wyvern_combat import prove_damage_source

        prove_damage_source(
            game, c, state, source_work, target, asset_id, event, actor, chooser_controller
        )
    elif source_work and any(
        x.id == source_work and x.kind == "damage"
        for x in changeling_records(state, ChangelingFingers)
    ):
        from girlframe.services.m3_changeling_effects import (
            prove_damage_source as prove_fingers_damage,
        )

        prove_fingers_damage(
            game, c, state, source_work, target, asset_id, event, actor, chooser_controller
        )
    elif source_work and any(x.id == source_work for x in ankou_records(state, AnkouTouch)):
        from girlframe.services.m3_ankou import prove_touch, validate_pending_touch

        touch = next(x for x in ankou_records(state, AnkouTouch) if x.id == source_work)
        if touch.event == event:
            validate_pending_touch(game, c, state, touch.id, event)
        else:
            touch = prove_touch(game, c, state, touch.id)
        if (
            touch.completed_event is not None
            or target != touch.actor
            or actor != touch.actor
            or asset_id != touch.asset
            or chooser_controller
            != resolve(state, touch.actor, bound, require_current_profile=False).controller
        ):
            raise WorkflowError("Damage only the original Relay user's selected real Asset")
    elif source_work and any(x.id == source_work for x in easy_target_records(state, NpcHurt)):
        from girlframe.services.m3_easy_target import prove_npc_hurt_damage

        prove_npc_hurt_damage(
            game, c, state, source_work, target, asset_id, event, actor, chooser_controller
        )
    elif (
        source_action
        and occurrence == "am_scrutinized_pilot"
        and game.action(c, source_action)["data"].get("am_scrutinized", {}).get("pilot_damage")
    ):
        from girlframe.services.m3_am_scrutinized import validate_pending_pilot_damage

        validate_pending_pilot_damage(
            game,
            c,
            state,
            game.action(c, source_action),
            target,
            asset_id,
            event,
            actor,
            chooser_controller,
        )
    elif actor is not None:
        frozen_original = False
        if source_action and actor.kind == "pilot" and rules.original_ended(state, actor):
            from girlframe.services.m3_battle_dormant import proved_converted_originals

            original_action = game.action(c, source_action)
            original_meta = original_action["data"].get("battle", {})
            allowed = proved_converted_originals(game, c, state, original_action)
            frozen_original = (actor.entity, str(actor.incarnation)) in allowed and (
                original_action["data"]["play"] == "all_out_assault"
                and original_action["data"].get("result", {}).get("tier") in ("mid", "high")
                and original_meta.get("actor") == actor.model_dump(mode="json")
                and original_meta.get("target") == target.model_dump(mode="json")
                and original_meta.get("target_asset") == asset_id
                and occurrence == "assault"
                and original_meta.get("actor_controller") == chooser_controller
            )
        if not frozen_original:
            actual = resolve(state, actor, bound, require_current_profile=False)
            if chooser_controller is not None and actual.controller != chooser_controller:
                raise WorkflowError("Use the original source actor's actual human controller.")
            chooser_controller = actual.controller
    if source_action:
        action = game.action(c, source_action)
        if action["state"] in ("complete", "aborted"):
            raise WorkflowError("Apply damage through its actual still-held source Play.")
    stamp = str(
        uuid5(
            NAMESPACE_URL,
            "girlframe:battle-damage:" + event + ":" + target.token + ":" + occurrence,
        )
    )
    if any(x.get("kind") == "battle_damage_stage" and x.get("id") == stamp for x in state.facts):
        raise WorkflowError("This actual damage occurrence already has its original effect.")
    if allow_sprite:
        from girlframe.services.m3_sprite import defer, physical_incoming

        if physical_incoming(game, c, source_action, occurrence, physical_blow):
            deferred, interceptions = defer(
                game,
                c,
                state,
                target=target,
                asset=asset_id,
                source_action=source_action,
                source_work=source_work,
                event=event,
                opponent=opponent or actor,
                chooser=chooser_controller,
                occurrence=occurrence,
                indirect=indirect,
            )
            if interceptions:
                return deferred, interceptions
    source_inside = None
    if source_action:
        source_data = game.action(c, source_action)["data"]
        source_inside = source_data.get("battle", {}).get("occupancy", {}).get(target.token)
        if source_inside is None and source_data.get("snoop"):
            source_inside = source_data["snoop"].get("occupancy", {}).get(target.token)
    changed, required = rules.damage(
        state,
        target,
        asset_id,
        bound,
        event,
        opponent=opponent or actor,
        indirect=indirect,
        inside_frame=source_inside,
    )
    foe = opponent or actor
    if (
        foe is not None
        and foe.kind == "gorgon"
        and state.world is not None
        and any(x.id == foe.entity and x.gorgon_class == "aggressive" for x in state.world.gorgons)
        and any(x.kind in ("defeat", "harpy_defeat") for x in required)
    ):
        aggressive_id = str(uuid5(NAMESPACE_URL, stamp + ":0"))
        required = (
            Required(kind="aggressive_damage", target=target, opponent=foe, source_pdf=165),
        ) + tuple(
            x.model_copy(update=dict(details=x.details | dict(aggressive=aggressive_id)))
            if x.kind in ("defeat", "harpy_defeat")
            else x
            for x in required
        )
    ids: list[str] = []
    for index, obligation in enumerate(required):
        identity = str(uuid5(NAMESPACE_URL, stamp + ":" + str(index)))
        if obligation.kind in ("npc_damage",) and chooser_controller is None:
            raise WorkflowError("The actual attacker owns the NPC damage replacement choice.")
        if obligation.kind in ("handler_damage", "handler_helpless"):
            from girlframe.services.m3_handler_consequences import require

            changed, consequence = require(
                game,
                c,
                changed,
                target,
                trigger="asset_damage",
                source_action=source_action,
                source_event=event,
                opponent=opponent or actor,
                source_work=source_work,
                choice_kind="combat_handler_consequence",
                occurrence=occurrence,
            )
            obligation = obligation.model_copy(update={"details": {"consequence": consequence}})
        changed.facts.append(
            dict(
                kind="battle_damage_stage",
                id=identity,
                stamp=stamp,
                event=event,
                source_action=source_action or "",
                source_work=source_work or "",
                requirement=obligation.model_dump_json(),
                chooser=str(chooser_controller or 0),
            )
        )
        ids.append(identity)
    changed.facts.append(
        dict(
            kind="battle_damage_stage",
            id=stamp,
            event=event,
            applied=target.model_dump_json(),
            asset=asset_id or "",
        )
    )
    from girlframe.engine.m3_appearance_matrix import record_damage

    scene = game.action(c, source_action)["scene_id"] if source_action else None
    if scene is None and source_work:
        from girlframe.engine.m3_ankou import Encounter as AnkouEncounter

        scope_touch = next(
            (x for x in ankou_records(state, AnkouTouch) if x.id == source_work), None
        )
        if scope_touch is not None:
            encounter = next(
                x for x in ankou_records(state, AnkouEncounter) if x.id == scope_touch.encounter
            )
            scene = encounter.cast.id
    if scene is None and source_work:
        mental = next(
            (
                x
                for x in changeling_records(state, ChangelingFingers)
                if x.id == source_work and x.kind == "damage"
            ),
            None,
        )
        if mental is not None:
            scene = mental.cast.id
    if scene is None and source_work:
        use = next((x for x in wyvern_records(state, RousedUse) if x.id == source_work), None)
        if use is not None:
            scene = use.cast.id
    if scene is None and source_work:
        work = t.m3["m3_required_work"]
        scene = c.scalar(
            sa.select(work.c.scene_id)
            .where(work.c.campaign_id == game.store.campaign_id, work.c.id == source_work)
            .order_by(work.c.revision.desc())
            .limit(1)
        )
    record_damage(
        state,
        changed,
        damager=actor or opponent,
        target=target,
        identity=asset_id,
        scene=scene,
        event=event,
        action=source_action,
        work=source_work,
        occurrence=occurrence,
    )
    from girlframe.services.m3_easy_target import observe_harm
    from girlframe.services.m3_sprite import physical_incoming

    observe_harm(
        game,
        c,
        state,
        changed,
        target=target,
        opponent=opponent or actor,
        event=event,
        source_action=source_action,
        source_work=source_work,
        physical_blow=physical_incoming(game, c, source_action, occurrence, physical_blow),
    )
    return changed, tuple(ids)


def damage_frame_at_scene(
    game: "GameService",
    c: Connection,
    state: GameState,
    *,
    target: ActorRef,
    frame_instance: str,
    asset_id: str,
    source_action: str | None,
    event: str,
    actor: ActorRef,
    chooser_controller: int,
    occurrence: str,
    source_work: str | None = None,
    allow_sprite: bool = True,
) -> tuple[GameState, tuple[str, ...]]:
    """Actual Snoop damage to a proven current vacant Frame, never its absent Girl."""
    from girlframe.engine.m3_physical import occupied_frame
    from girlframe.services.m3_enforcer_snoop import validate_frame_damage_source

    use = None
    if source_action is not None:
        validate_frame_damage_source(
            c, game, state, source_action, target, frame_instance, asset_id
        )
    else:
        if source_work is None:
            raise WorkflowError("A parked Frame effect needs its actual original source")
        from girlframe.engine.m3_ankou import Touch as FrameTouch
        from girlframe.engine.m3_ankou import records as frame_touches

        touch = next((x for x in frame_touches(state, FrameTouch) if x.id == source_work), None)
        if touch is not None:
            from girlframe.services.m3_ankou import prove_touch, validate_pending_touch

            if touch.event == event:
                validate_pending_touch(game, c, state, touch.id, event)
            else:
                touch = prove_touch(game, c, state, touch.id)
            if (
                touch.completed_event
                or actor != touch.actor
                or target != touch.actor
                or frame_instance != touch.frame
                or asset_id != touch.asset
                or chooser_controller != int(touch.actor.entity)
            ):
                raise WorkflowError(
                    "Pay only the exact original Relay user's real Frame Asset cost"
                )
        else:
            from girlframe.services.m3_wyvern_combat import prove_damage_source

            use = prove_damage_source(
                game, c, state, source_work, target, asset_id, event, actor, chooser_controller
            )
            if use.target_frame != frame_instance:
                raise WorkflowError("Preserve the actual selected parked Frame, not another body")
    if target.kind != "pilot":
        raise WorkflowError("The actual assigned Frame port requires its original Pilot owner.")
    from girlframe.services.m3_wyvern_combat import require_damage_allowed

    require_damage_allowed(game, c, state, target)
    bound = profiles(c, game.store.campaign_id)
    actual = resolve(state, target, bound, require_current_profile=False)
    if actual.frame_instance != frame_instance:
        raise WorkflowError(
            "The discovered Frame instance has changed; do not damage its replacement."
        )
    body = next((x for x in state.placements if x.actor == target), None)
    if body is None:
        raise WorkflowError("Record actual original cockpit occupancy before damaging this Frame.")
    if use is not None and allow_sprite:
        from girlframe.services.m3_sprite import defer

        deferred, interceptions = defer(
            game,
            c,
            state,
            target=target,
            asset=asset_id,
            source_action=None,
            source_work=source_work,
            event=event,
            opponent=actor,
            chooser=chooser_controller,
            occurrence=occurrence,
            target_frame=frame_instance,
        )
        if interceptions:
            return deferred, interceptions
    occupants = [x for x in state.placements if occupied_frame(x) == (target, frame_instance)]
    if occupants:
        if any(x.actor != target for x in occupants):
            raise WorkflowError("This occupied Frame needs its actual occupant consequence port.")
        return damage_actor(
            game,
            c,
            state,
            target=target,
            asset_id=asset_id,
            source_action=source_action,
            source_work=source_work,
            event=event,
            actor=actor,
            chooser_controller=chooser_controller,
            occurrence=occurrence,
            physical_blow=use is not None,
            allow_sprite=False,
        )
    if body.mode != "outside_frame":
        raise WorkflowError("Prove actual vacancy; missing or passenger facts are not permission.")
    sheet = state.sheets[target.entity]
    runtime = sheet.frame_runtime
    if (runtime and runtime.core_id) or (runtime is None and sheet.frame in ("JANUS", "JANUS-B")):
        raise WorkflowError(
            "An inhabited independent Core requires its own actual control/damage port."
        )
    selected = next((x for x in sheet.assets if x.id == asset_id and x.family == "frame"), None)
    if selected is None or selected.damaged:
        raise WorkflowError("Choose an actual intact Asset of this exact discovered Frame.")
    changed = GameState.model_validate_json(state.model_dump_json())
    destination = changed.sheets[target.entity]
    for item in destination.assets:
        if item.id == asset_id:
            item.damaged = True
    destination.revision += 1
    changed.facts.append(
        dict(
            kind="vacant_frame_asset_damaged",
            actor=target.model_dump_json(),
            frame=frame_instance,
            asset=asset_id,
            source_action=source_action or "",
            **({"source_work": source_work} if source_work is not None else {}),
            event=event,
            occurrence=occurrence,
            disabled=str(
                not any(x.family == "frame" and not x.damaged for x in destination.assets)
            ),
        )
    )
    from girlframe.engine.m3_appearance_matrix import record_damage

    record_damage(
        state,
        changed,
        damager=actor,
        target=target,
        identity=asset_id,
        scene=game.action(c, source_action)["scene_id"]
        if source_action
        else use.cast.id
        if use
        else None,
        event=event,
        action=source_action,
        work=source_work,
        occurrence=occurrence,
    )
    return changed, ()


def require_director_helpless(
    game: "GameService",
    c: Connection,
    state: GameState,
    *,
    target: ActorRef,
    opponent: ActorRef,
    source_action: str,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    bound = profiles(c, game.store.campaign_id)
    actual = resolve(state, target, bound, require_current_profile=False)
    foe = resolve(state, opponent, bound, require_current_profile=False)
    if actual.rules != "director" or target.kind != "npc":
        raise WorkflowError("Only this actual Director uses its Handler-rule Helpless choice.")
    action = game.action(c, source_action)
    if not action["data"].get("enforcement") or action["state"] in ("complete", "aborted"):
        raise WorkflowError("Recover the exact held Enforcer source of this Director Helplessness.")
    identity = str(uuid5(NAMESPACE_URL, "actual-director-helpless:" + event + ":" + target.token))
    if any(x.get("id") == identity for x in state.facts):
        raise WorkflowError("This actual Director Helpless trigger already exists.")
    changed = GameState.model_validate_json(state.model_dump_json())
    required = Required(kind="director_helpless", target=target, opponent=opponent, source_pdf=15)
    changed.facts.append(
        dict(
            kind="battle_damage_stage",
            id=identity,
            stamp=identity,
            event=event,
            source_action=source_action,
            source_work="",
            requirement=required.model_dump_json(),
            chooser=str(foe.controller),
        )
    )
    return changed, (identity,)


def npc_flirt_escape(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    choice_id: str,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    """Only the original NPC's genuine selected Flirt escape grants this self-cost."""
    from girlframe.engine import m3_battle_npc as npc_rules
    from girlframe.services.m3_npc_flirt import validate_pending_escape_damage

    scope = validate_pending_escape_damage(game, c, state, action, choice_id, event)
    target = ActorRef.model_validate(scope["target"])
    source_actor = ActorRef.model_validate(scope["actor"])
    scene = SceneCast.model_validate_json(json.dumps(scope["cast"]))
    actual = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        scope["action"] != action["id"]
        or scope["source_event"] != event
        or scope["source_choice"] != choice_id
        or scope["physical_blow"] is not False
        or source_actor != target
        or target.kind != "npc"
        or actual.rules != "npc"
        or actual.controller != scope["chooser"]
    ):
        raise WorkflowError("Use only the actual original NPC's genuine escape self-cost")
    identity = npc_rules.escape_damage_id(scope["id"])
    source = npc_rules.FlirtSelfDamage(
        id=identity,
        damage=scope["id"],
        action=action["id"],
        choice=choice_id,
        npc=target,
        controller=scope["chooser"],
        cast=scene,
        event=event,
    )
    changed = GameState.model_validate_json(state.model_dump_json())
    prior = next(
        (
            value
            for value in changed.facts
            if value.get("kind") == "npc_flirt_self_damage" and value.get("id") == identity
        ),
        None,
    )
    if prior is not None:
        if npc_rules.self_damage(changed, identity) != source:
            raise WorkflowError("Preserve the original actual NPC damage source")
        return changed, (identity,)
    required = Required(
        kind="npc_damage",
        target=target,
        opponent=target,
        source_pdf=15,
        details={"source_kind": npc_rules.SELF_SOURCE, "source_damage": source.damage},
    )
    changed.facts.append(
        dict(kind="npc_flirt_self_damage", id=identity, body=source.model_dump_json())
    )
    changed.facts.append(
        dict(
            kind="battle_damage_stage",
            id=identity,
            stamp=identity,
            event=event,
            source_action=action["id"],
            source_work="",
            chooser=str(source.controller),
            source_kind=npc_rules.SELF_SOURCE,
            source_choice=choice_id,
            source_damage=source.damage,
            requirement=required.model_dump_json(),
        )
    )
    return changed, (identity,)


def synchronize_damage(game: "GameService", c: Connection, event: str) -> None:
    """Materialize only staged facts present in the immutable actual event's canonical history."""
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Save the actual damage event before creating its continuation work.")
    state = GameState.model_validate_json(raw)
    work = t.m3["m3_required_work"]
    for fact in state.facts:
        if fact.get("kind") != "battle_damage_stage" or fact.get("event") != event:
            continue
        if "requirement" not in fact or c.scalar(
            sa.select(work.c.id).where(
                work.c.campaign_id == game.store.campaign_id, work.c.id == fact["id"]
            )
        ):
            continue
        obligation = Required.model_validate_json(fact["requirement"])
        source_action = fact.get("source_action") or None
        action = game.action(c, source_action) if source_action else None
        parent = dict(campaign_id=game.store.campaign_id, campaign_context=True)
        if action:
            parent = dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"])
        if action is None and fact.get("source_work"):
            from girlframe.engine.m3_wyvern import RousedUse
            from girlframe.engine.m3_wyvern import records as wyvern_records
            from girlframe.services.m3_wyvern import prove_use

            source_use = next(
                (x for x in wyvern_records(state, RousedUse) if x.id == fact["source_work"]), None
            )
            if source_use is not None:
                prove_use(game, c, state, source_use.id)
                parent = dict(campaign_id=game.store.campaign_id, scene_id=source_use.cast.id)
            else:
                source_row = (
                    c.execute(
                        sa.select(work)
                        .where(
                            work.c.campaign_id == game.store.campaign_id,
                            work.c.id == fact["source_work"],
                        )
                        .order_by(work.c.revision.desc())
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                if source_row is not None:
                    parent = dict(source_row)
        actual = resolve(
            state,
            obligation.target,
            profiles(c, game.store.campaign_id),
            require_current_profile=False,
        )
        owner = int(fact["chooser"]) if obligation.kind == "npc_damage" else actual.controller
        if obligation.kind == "aggressive_damage":
            if obligation.opponent is None:
                raise WorkflowError(
                    "Recover the actual Aggressive attacker for this immediate hit."
                )
            owner = resolve(state, obligation.opponent, ()).controller
        body: dict[str, Any] = dict(
            owner=obligation.target.model_dump(mode="json"),
            character=obligation.target.incarnation,
            source_action=source_action,
            source_work=fact.get("source_work") or None,
            requirement=obligation.model_dump(mode="json"),
            immediate=True,
        )
        if obligation.kind == "sprite_intercept":
            from girlframe.services.m3_sprite import materialize as materialize_sprite

            materialize_sprite(game, c, fact, obligation, body, parent, action, event)
            continue
        if obligation.kind == "npc_damage" and fact.get("source_kind") == "npc_flirt_escape":
            from girlframe.services.m3_battle_npc import prove_flirt_self_damage

            source = prove_flirt_self_damage(game, c, state, fact["id"])
            if (
                obligation.target != source.npc
                or obligation.opponent != source.npc
                or source.action != source_action
                or owner != source.controller
            ):
                raise WorkflowError("Keep the real NPC self-cost and original controller")
            body.update(
                source_kind="npc_flirt_escape",
                source_choice=source.choice,
                source_damage=source.damage,
                damage_source_event=source.event,
            )
        if obligation.kind == "npc_damage":
            source_handler, source_appointment = MedicalService(game.store)._handler(c)
            body.update(handler=source_handler, appointment=source_appointment)
        if action:
            choice = game.request(
                c,
                action,
                owner,
                "snoop_damage_consequence"
                if action["data"].get("snoop")
                else "enforcer_director_consequence"
                if action["data"].get("enforcement")
                and obligation.kind in ("director_damage", "director_helpless")
                else "battle_" + obligation.kind,
                dict(work_id=fact["id"], **body),
            )
            body["continuation"] = choice
            game.save_action(c, action)
        related(
            c,
            game.store,
            parent,
            fact["id"],
            owner,
            actual.controller,
            obligation.kind,
            body,
            event,
        )


def complete_damage_work(
    game: "GameService",
    c: Connection,
    row: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    """Notify only the actual source effect grant once its real work has resolved."""
    work = t.m3["m3_required_work"]
    latest = (
        c.execute(
            sa.select(work)
            .where(work.c.campaign_id == game.store.campaign_id, work.c.id == row["id"])
            .order_by(work.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if latest is None or latest["state"] != "resolved":
        raise WorkflowError("Finish this actual source-required consequence first.")
    body = json.loads(latest["body_json"])
    state = load_state(c, game.store.campaign_id)
    if body.get("continuation") and body.get("source_action"):
        choices = t.m2["m2_choices"]
        request = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.id == body["continuation"],
                )
            )
            .mappings()
            .first()
        )
        if (
            request is None
            or request["action_id"] != body["source_action"]
            or json.loads(request["body_json"]).get("work_id") != row["id"]
        ):
            raise WorkflowError("Recover the actual source-required damage continuation.")
        c.execute(
            choices.update()
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == request["id"],
                choices.c.state == "pending",
            )
            .values(state="completed_by_work", revision=choices.c.revision + 1)
        )
    if body.get("source_kind") == "npc_flirt_escape":
        from girlframe.services.m3_battle_npc import prove_flirt_self_damage
        from girlframe.services.m3_npc_flirt import complete_damage_work as complete_flirt_escape

        source = prove_flirt_self_damage(game, c, state, row["id"])
        if body.get("source_action") != source.action or not complete_flirt_escape(
            game, c, dict(latest), event
        ):
            raise WorkflowError("Complete only this actual NPC Flirt self-cost source")
        return
    if body.get("source_work"):
        from girlframe.services.m3_sprite import complete_children

        if complete_children(game, c, body["source_work"], event, viewer, key):
            return
    if any(x.id == body.get("source_work") for x in state.handler_plays):
        from girlframe.services.m3_handler_plays import complete_damage

        complete_damage(game, c, body["source_work"], event, viewer, key)
    if body.get("source_work"):
        from girlframe.services.m3_wyvern_combat import complete_damage_work as complete_wyvern

        complete_wyvern(game, c, dict(latest), event, viewer, key)
    if body.get("source_action"):
        action = game.action(c, body["source_action"])
        if action["data"].get("am_scrutinized", {}).get("pilot_damage"):
            from girlframe.services.m3_am_scrutinized import complete_pilot_damage

            complete_pilot_damage(game, c, dict(latest), event, viewer, key)
        elif action["data"].get("consume"):
            from girlframe.services.m3_consume import synchronize as synchronize_consume

            synchronize_consume(game, c, action, event)
        elif action["data"].get("battle"):
            synchronize(game, c, action, event, viewer, key)
        elif action["data"].get("gorgon_play"):
            from girlframe.services.m3_gorgon_play import (
                complete_damage_work as complete_gorgon_damage,
            )

            complete_gorgon_damage(game, c, dict(latest), event, viewer, key)
        elif action["data"].get("snoop"):
            from girlframe.services.m3_enforcer_snoop import complete_damage as complete_snoop

            complete_snoop(game, c, action, dict(latest), event, viewer, key)
        elif action["data"].get("enforcement"):
            from girlframe.services.m3_enforcement_initiative import complete_director_consequence

            complete_director_consequence(game, c, action, dict(latest), event, viewer, key)
        elif action["data"].get("easy_target") and body.get("source_work"):
            from girlframe.services.m3_easy_target import complete_npc_hurt_work

            complete_npc_hurt_work(game, c, dict(latest), event)
        elif action["data"].get("newgirl_sex"):
            from girlframe.services.m3_newgirl_sex import synchronize as synchronize_newgirl_sex

            synchronize_newgirl_sex(game, c, action, event)
        elif action["data"].get("casualty_sex"):
            from girlframe.services.m3_casualty import synchronize as synchronize_casualty_sex

            synchronize_casualty_sex(game, c, action, event)
        elif action["data"].get("vatgrown_sex"):
            from girlframe.services.m3_vatgrown_plays import synchronize as synchronize_vatgrown_sex

            synchronize_vatgrown_sex(game, c, action, event)
        elif action["data"].get("alpha_sex"):
            from girlframe.services.m3_alpha_sex import synchronize as synchronize_alpha_sex

            synchronize_alpha_sex(game, c, action, event)
        elif action["data"].get("alpha"):
            from girlframe.services.m3_alpha import synchronize as synchronize_alpha

            synchronize_alpha(game, c, action, event)
        elif action["data"].get("clone_flirt"):
            from girlframe.services.m3_clone_am_plays import synchronize as sync_clone

            sync_clone(game, c, action, event)
        elif action["data"].get("engage"):
            from girlframe.services.m3_engage import complete_damage_work as complete_engage_damage

            complete_engage_damage(game, c, dict(latest), event, viewer, key)
        if action["data"].get("investment_performance"):
            from girlframe.services.m3_vatgrown_plays import synchronize_investment_performance

            synchronize_investment_performance(game, c, game.action(c, action["id"]), event)
        if action["data"].get("easy_target_child"):
            from girlframe.services.m3_easy_target import synchronize as synchronize_easy_child

            synchronize_easy_child(game, c, game.action(c, action["id"]), event)
    from girlframe.services.m3_consume import resume_pending as resume_consume

    resume_consume(game, c, event)


def damage_prerequisites(game: "GameService", c: Connection, row: dict[str, Any]) -> None:
    from girlframe.services.m3_collateral import latest

    body = json.loads(row["body_json"])
    if str(body.get("source_work", "")).startswith("a-bomb-drop:"):
        from girlframe.services.m3_a_bomb import prove_drop

        source_state = load_state(c, game.store.campaign_id)
        source = prove_drop(game, c, source_state, body["source_work"])
        if not any(
            row["id"] in x.work and x.actor.model_dump(mode="json") == body.get("owner")
            for x in source.resources
        ):
            raise WorkflowError("Recover the exact original nuclear damage requirement")
    if body.get("source_work"):
        from girlframe.engine.m3_wyvern import RousedUse
        from girlframe.engine.m3_wyvern import records as wyvern_records
        from girlframe.services.m3_wyvern import prove_use

        source_state = load_state(c, game.store.campaign_id)
        if any(x.id == body["source_work"] for x in wyvern_records(source_state, RousedUse)):
            source_use = prove_use(game, c, source_state, body["source_work"])
            if row["id"] not in source_use.work:
                raise WorkflowError("Recover the actual Roused strike's original required work")
    aggressive = body.get("requirement", {}).get("details", {}).get("aggressive")
    if aggressive:
        other = latest(game, c, aggressive)
        sibling = json.loads(other["body_json"])
        if (
            other["kind"] != "aggressive_damage"
            or sibling.get("owner") != body.get("owner")
            or sibling.get("source_action") != body.get("source_action")
        ):
            raise WorkflowError("Recover the exact original Aggressive sibling consequence.")
        if other["state"] != "resolved":
            raise WorkflowError(
                "Resolve the actual Aggressive immediate Girl-Asset choice before Defeat can roll."
            )


def source_parent_for_defeat(
    game: "GameService",
    c: Connection,
    row: dict[str, Any],
    actor: ActorRef,
) -> str | None:
    """Prove the frozen original actual Asset exhaustion rather than a caller-chosen parent."""
    body = json.loads(row["body_json"])
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == row["event_id"],
        )
    )
    state = GameState.model_validate_json(raw) if raw else None
    fact = (
        next(
            (
                x
                for x in state.facts
                if x.get("kind") == "battle_damage_stage"
                and x.get("id") == row["id"]
                and "requirement" in x
            ),
            None,
        )
        if state
        else None
    )
    required = Required.model_validate_json(fact["requirement"]) if fact else None
    if (
        required is None
        or required.kind != "defeat"
        or required.target != actor
        or body.get("owner") != actor.model_dump(mode="json")
        or body.get("character") != actor.incarnation
    ):
        raise WorkflowError("SOURCE_BATTLE_DAMAGE_MISSING: recover the actual original exhaustion.")
    damage_prerequisites(game, c, row)
    parent = body.get("source_action")
    return str(parent) if parent is not None else None


def complete_handler_consequence(
    game: "GameService",
    c: Connection,
    record: Any,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> bool:
    """The actual Handler replacement closes only work proven by its original staged source."""
    state = load_state(c, game.store.campaign_id)
    if record.state == "pending" or not record.effect_event:
        raise WorkflowError("Finish the actual Handler-owned consequence first.")
    requirements = []
    for fact in state.facts:
        if fact.get("kind") == "battle_damage_stage" and "requirement" in fact:
            required = Required.model_validate_json(fact["requirement"])
            if required.details.get("consequence") == record.id:
                requirements.append(fact)
    if not requirements:
        return False
    work = t.m3["m3_required_work"]
    for fact in requirements:
        row = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == game.store.campaign_id, work.c.id == fact["id"])
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Recover the actual original staged Handler damage work.")
        body = json.loads(row["body_json"])
        if row["state"] != "resolved":
            c.execute(
                work.insert().values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                    body_json=json.dumps(
                        body
                        | dict(
                            resolution="actual_handler_replacement",
                            consequence=record.id,
                            effect_event=record.effect_event,
                        )
                    ),
                )
            )
        if body.get("continuation"):
            choices = t.m2["m2_choices"]
            c.execute(
                choices.update()
                .where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.id == body["continuation"],
                    choices.c.state == "pending",
                )
                .values(state="completed_by_work", revision=choices.c.revision + 1)
            )
        complete_damage_work(game, c, dict(row), event, viewer, key)
        if body.get("source_action") and viewer is not None:
            action = game.action(c, body["source_action"])
            if action["data"].get("battle"):
                synchronize(game, c, action, event, viewer, key)
    return True


def complete_handler_play(
    game: "GameService",
    c: Connection,
    grant: "HandlerPlay",
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    """Accept only an actual completed effect or an explicitly owned optional decline."""
    if (
        grant.state not in ("complete", "declined")
        or grant.source not in ("battle_counter", "required")
        or (grant.state == "declined" and grant.source != "battle_counter")
    ):
        raise WorkflowError("Finish the actual scoped counter Play or explicitly decline it.")
    if not grant.source_action or not grant.source_choice:
        raise WorkflowError("Recover the original counter source choice.")
    action = game.action(c, grant.source_action)
    pending = next(
        (
            x
            for x in game.pending(c, action["id"])
            if x["kind"] == "battle_handler_play"
            and json.loads(x["body_json"]).get("grant_id") == grant.id
        ),
        None,
    )
    if pending is None:
        return
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == pending["id"],
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    action["data"].setdefault("battle_completed", {})[grant.id] = event
    game.save_action(c, action)
    if action["data"].get("battle"):
        synchronize(game, c, action, event, viewer, key)


def complete_counter_play(
    game: "GameService",
    c: Connection,
    child: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    """A genuine completed owned child releases its exact frozen original target's counter."""
    if child["state"] != "complete" or not child.get("parent_id"):
        raise WorkflowError("Finish the actual source-bound counter child Play first.")
    parent = game.action(c, child["parent_id"])
    meta = parent["data"].get("battle")
    if meta is None:
        raise WorkflowError("Recover the actual source battle parent.")
    expected = ActorRef.model_validate_json(json.dumps(meta["target"]))
    actual = child["data"].get("actor_basic", {}).get("ref") or child["data"].get("battle", {}).get(
        "actor"
    )
    if actual is None and expected.kind == "pilot":
        ids = child["data"].get("character_ids", {})
        if (
            child["actor_id"] == expected.entity
            and ids.get(expected.entity) == expected.incarnation
        ):
            actual = expected.model_dump(mode="json")
    if actual != expected.model_dump(mode="json"):
        raise WorkflowError(
            "A successor or different actor cannot satisfy the original target's counter."
        )
    source = child["data"].get("battle_counter_source", {})
    if source.get("actor") != meta["target"] or source.get("attacker") != meta["actor"]:
        raise WorkflowError("Recover the actual frozen counter-child source binding.")
    pending = next(
        (
            x
            for x in game.pending(c, parent["id"])
            if x["kind"] == "battle_counter_play"
            and x["id"] == source.get("choice")
            and json.loads(x["body_json"]).get("actor") == meta["target"]
            and json.loads(x["body_json"]).get("attacker") == meta["actor"]
        ),
        None,
    )
    if pending is None:
        return
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == pending["id"],
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    meta.setdefault("counter_children", []).append(dict(child=child["id"], event=event))
    game.save_action(c, parent)
    synchronize(game, c, parent, event, viewer, key)


def validate_counter_child(
    game: "GameService",
    c: Connection,
    parent: dict[str, Any],
    actor: ActorRef,
    prepared: PlayInput,
) -> dict[str, Any]:
    """One printed counter, exact original two bodies, no general permission for nested Plays."""
    meta = parent["data"].get("battle")
    if (
        meta is None
        or parent["state"] in ("complete", "aborted")
        or meta.get("target") != actor.model_dump(mode="json")
    ):
        raise WorkflowError("Only this actual original target can make its one source counter.")
    row = next(
        (
            x
            for x in game.pending(c, parent["id"])
            if x["kind"] == "battle_counter_play"
            and json.loads(x["body_json"]).get("actor") == meta["target"]
            and json.loads(x["body_json"]).get("attacker") == meta["actor"]
        ),
        None,
    )
    actual = resolve(
        load_state(c, game.store.campaign_id),
        actor,
        profiles(c, game.store.campaign_id),
        require_current_profile=False,
    )
    if (
        row is None
        or row["actor_id"] != str(actual.controller)
        or actual.controller != meta["target_controller"]
    ):
        raise WorkflowError(
            "Recover the original source target's actual controller and pending counter."
        )
    attacker = ActorRef.model_validate_json(json.dumps(meta["actor"]))
    if prepared.target_actor is not None and prepared.target_actor != attacker:
        raise WorkflowError("This actual counter can only target its original attacker.")
    if prepared.target is not None and (
        attacker.kind != "pilot" or prepared.target != int(attacker.entity)
    ):
        raise WorkflowError("The human target selector must name the actual original attacker.")
    if prepared.parent != parent["id"] or prepared.source_work:
        raise WorkflowError("Use the actual held parent, without another required-work source.")
    return row


class BattleService:
    """Owned declaration followed by actual adjudication, before consuming any dice."""

    def __init__(self, store: OnboardingStore):
        from girlframe.services.m2_game import GameService

        self.store, self.game = store, GameService(store)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        latest = {
            x["id"]: Context.model_validate_json(x["body"])
            for x in state.facts
            if x.get("kind") == "battle_context"
        }
        used = {x["context"] for x in state.facts if x.get("kind") == "battle_context_used"}
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Battle opening: " + x.declaration.play,
                incoming=viewer.user_id == x.adjudicator,
                state=x.state,
                scene=x.scene,
                source_action=x.source_action,
            )
            for x in latest.values()
            if x.id not in used
            and (
                (x.state == "proposed" and viewer.user_id in (x.owner, x.adjudicator))
                or (x.state == "confirmed" and viewer.user_id == x.owner)
            )
        ]

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return self._tasks(c, viewer)

    def context(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            fact = next(
                (
                    x
                    for x in reversed(state.facts)
                    if x.get("kind") == "battle_context" and x.get("id") == identity
                ),
                None,
            )
            value = Context.model_validate_json(fact["body"]) if fact else None
            if value is None or viewer.user_id not in (
                value.owner,
                value.source_author,
                value.adjudicator,
            ):
                raise WorkflowError(
                    "This saved battle context belongs to its actual source humans."
                )
            channel = c.scalar(
                sa.select(t.m2["m2_scenes"].c.channel_id).where(
                    t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_scenes"].c.id == value.scene,
                )
            )
            princess_child = None
            if value.source_work:
                from girlframe.engine import m3_princess_sex as princess
                from girlframe.services.m3_princess_sex import child_projection

                direction = next(
                    (x for x in princess.directions(state) if x.id == value.source_work), None
                )
                if direction is not None and viewer.user_id == direction.author_controller:
                    princess_child = child_projection(self.game, c, state, direction.id)
            rider: dict[str, Any] | None = None
            if viewer.user_id == value.owner and value.declaration.play == "all_out_assault":
                from girlframe.services.m3_learned_plays import (
                    NO_ONE_BETTER,
                    available,
                    consumed_no_one_better,
                )

                rows = c.scalars(
                    sa.select(t.m2["m2_actions"].c.id).where(
                        t.m2["m2_actions"].c.campaign_id == self.store.campaign_id,
                        sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.battle.context")
                        == identity,
                    )
                ).all()
                for action_id in rows:
                    action = self.game.action(c, action_id)
                    if action["data"].get("learned_no_one_better", {}).get("resolved_event"):
                        spent = consumed_no_one_better(self.game, c, state, action)
                        rider = dict(
                            action=action_id,
                            state=action["state"],
                            text="No One Better was spent once on this high Assault."
                            if spent
                            else "No One Better did not trigger; its lesson was released.",
                        )
                if (
                    rider is None
                    and available(self.game, c, state, value.declaration.actor, NO_ONE_BETTER)
                    is not None
                ):
                    rider = dict(
                        text=(
                            "Starting this Assault reserves your No One Better lesson. "
                            "Only a final 11+ spends it. Lower results keep their actual costs "
                            "and release the lesson."
                        )
                    )
            return dict(
                context=value.model_dump(mode="json"),
                channel=int(channel) if channel else None,
                revision=state.revision,
                princess_child=princess_child,
                **({"learned_rider": rider} if rider is not None else {}),
                source_work=value.source_work
                or (
                    c.scalar(
                        sa.select(
                            sa.func.json_extract(t.m2["m2_choices"].c.body_json, "$.work")
                        ).where(
                            t.m2["m2_choices"].c.campaign_id == self.store.campaign_id,
                            t.m2["m2_choices"].c.id == value.source_choice,
                        )
                    )
                    if value.source_action
                    and value.source_choice
                    and self.game.action(c, value.source_action)["data"].get("easy_target")
                    else None
                ),
            )

    def preview(
        self, viewer: GuildViewer, channel: int, *, required: PlayInput | None = None
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            bound = profiles(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            if cast is None or (
                cast.facilitator != viewer.user_id
                and not any(x.controller == viewer.user_id for x in cast.roles)
            ):
                raise WorkflowError("Join the actual scene cast before declaring combat.")
            required_actor = None
            required_controller = None
            if required is not None:
                source = _required_battle_child(self.game, c, viewer, state, required, channel)
                if source is None:
                    raise WorkflowError("Use a proved original required battle source")
                required_actor = ActorRef.model_validate(source["actor"])
                required_controller = resolve(
                    state, required_actor, bound, require_current_profile=False
                ).controller
            actors = []
            for role in cast.roles:
                if not _visible(state, role.actor, viewer.user_id):
                    continue
                if required_controller is not None and not _visible(
                    state, role.actor, required_controller
                ):
                    continue
                actual = resolve(state, role.actor, bound, require_current_profile=False)
                if actual.controller != role.controller:
                    raise WorkflowError("Recover the actual scene controller assignment.")
                owned = (
                    role.actor == required_actor
                    if required_actor is not None
                    else actual.controller == viewer.user_id
                )
                actors.append(
                    dict(
                        token=role.actor.token,
                        ref=role.actor.model_dump(mode="json"),
                        name=actual.label,
                        owned=owned,
                        rules=actual.rules,
                        girl=actual.girl,
                        piloting=actual.piloting,
                        heat=actual.heat,
                        gorgon_class=next(
                            (
                                x.gorgon_class
                                for x in state.world.gorgons
                                if x.id == role.actor.entity
                            ),
                            None,
                        )
                        if state.world and role.actor.kind == "gorgon"
                        else None,
                        sha256=rules.resource_sha(state, role.actor, bound),
                        assets=[
                            dict(id=x.id, name=x.name)
                            for x in rules.intact_assets(state, role.actor, bound)
                            if owned or not x.concealed
                        ],
                        core_assets=[
                            dict(id=x.id, name=x.name, damaged=x.damaged)
                            for x in rules.assets(state, role.actor, bound)
                            if owned or not x.concealed
                        ],
                    )
                )
            contexts: dict[str, Context] = {}
            for fact in state.facts:
                if fact.get("kind") == "battle_context":
                    item = Context.model_validate_json(fact["body"])
                    if item.scene == cast.id and viewer.user_id in (
                        item.owner,
                        item.source_author,
                        item.adjudicator,
                    ):
                        contexts[item.id] = item
            return dict(
                revision=state.revision,
                channel=channel,
                scene=cast.id,
                actors=actors,
                contexts=[x.model_dump(mode="json") for x in contexts.values()],
                required_actor=required_actor.model_dump(mode="json") if required_actor else None,
            )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        declaration: Declaration,
        *,
        parent: str | None = None,
        source_work: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_BATTLE: reopen the actual scene declaration.")
            source_grant = None
            if source_work is not None:
                from girlframe.engine import m3_princess_sex as princess

                direction = next(
                    (x for x in princess.directions(state) if x.id == source_work), None
                )
                prepared_source = PlayInput(
                    play=declaration.play,
                    context=direction.context if direction else declaration.account,
                    trigger_confirmed=True,
                    heat=0,
                    target_actor=declaration.target,
                    parent=parent,
                    source_work=source_work,
                )
                source_grant = _required_battle_child(
                    self.game, c, viewer, state, prepared_source, channel
                )
                if source_grant is None or source_grant["actor"] != declaration.actor.model_dump(
                    mode="json"
                ):
                    raise WorkflowError("Declare only this actual original required performance")
            source_choice = None
            if parent:
                source = self.game.action(c, parent)
                request: dict[str, Any] | None
                if source_grant is not None:
                    request = next(
                        (
                            x
                            for x in self.game.pending(c, parent)
                            if x["id"] == source_grant.get("choice")
                            and x["actor_id"] == str(viewer.user_id)
                        ),
                        None,
                    )
                elif source["data"].get("easy_target"):
                    from girlframe.services.m3_easy_target import battle_declaration

                    request = battle_declaration(self.game, c, source, declaration, viewer)
                elif source["data"].get("gorgon_play"):
                    from girlframe.services.m3_gorgon_play import counter_declaration

                    request = counter_declaration(self.game, c, source, declaration)
                else:
                    request = next(
                        (
                            x
                            for x in self.game.pending(c, parent)
                            if x["kind"] == "battle_counter_play"
                            and x["actor_id"] == str(viewer.user_id)
                            and json.loads(x["body_json"]).get("actor")
                            == declaration.actor.model_dump(mode="json")
                            and json.loads(x["body_json"]).get("attacker")
                            == declaration.target.model_dump(mode="json")
                        ),
                        None,
                    )
                if source["channel_id"] != str(channel) or request is None:
                    raise WorkflowError(
                        "Declare the actual target's counter against the original attacker."
                    )
                source_choice = request["id"]
            else:
                lock = self.game.lock(c, channel)
                if lock and lock["state"] != "released":
                    raise WorkflowError(
                        "SCENE_BUSY: a held source counter needs its actual parent."
                    )
            cast = _cast(self.game, c, state, channel)
            if cast is None or not all(
                any(x.actor == ref for x in cast.roles)
                for ref in (declaration.actor, declaration.target)
            ):
                raise WorkflowError("Both actual combatants must join this source scene.")
            bound = profiles(c, self.store.campaign_id)
            actor = resolve(state, declaration.actor, bound, require_current_profile=False)
            target = resolve(state, declaration.target, bound, require_current_profile=False)
            if actor.offstage_source is not None or target.offstage_source is not None:
                raise WorkflowError(
                    "A body in actual offstage travel cannot enter this battlefield declaration."
                )
            if not _visible(state, declaration.target, actor.controller):
                raise WorkflowError(
                    "Reveal the actual target in Conversation before declaring this attack."
                )
            controlled = bool(
                source_grant is not None
                and source_grant.get("author") == viewer.user_id
                and source_grant.get("actor_controller") == actor.controller
                and source_grant["actor"] == declaration.actor.model_dump(mode="json")
            )
            if (
                actor.controller != viewer.user_id
                and not controlled
                or rules.resource_sha(state, declaration.actor, bound) != declaration.actor_sha256
                or rules.resource_sha(state, declaration.target, bound) != declaration.target_sha256
            ):
                raise WorkflowError(
                    "Use your actual original actor and current opposing resources."
                )
            rules.owned_asset(
                state,
                declaration.actor,
                declaration.attacking_asset,
                bound,
                attacking=True,
                allow_damaged=declaration.play == "go_for_the_core",
            )
            if declaration.target_asset is not None:
                asset = rules.owned_asset(
                    state, declaration.target, declaration.target_asset, bound
                )
                if asset.concealed and target.controller != actor.controller:
                    raise WorkflowError(
                        "The opposing Asset must actually be revealed in Conversation."
                    )
            try:
                core = (
                    rules.core_available(state, declaration.target, declaration.actor, bound)
                    if declaration.play == "go_for_the_core"
                    else None
                )
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            handler, appointment = MedicalService(self.store)._handler(c)
            judge, judge_controller, judge_source = _scene_judge(self.game, c, state, cast)
            event = str(uuid4())
            context = Context(
                id=str(uuid4()),
                scene=cast.id,
                declaration=declaration,
                owner=actor.controller if controlled else viewer.user_id,
                source_author=viewer.user_id if controlled else None,
                adjudicator=handler,
                appointment=appointment,
                proposed_event=event,
                cast_revision=cast.revision,
                actor_position=actor.position_sha256,
                target_position=target.position_sha256,
                core_source=core,
                source_action=parent,
                source_choice=source_choice,
                source_work=source_work,
                judge_actor=judge,
                judge_controller=judge_controller,
                judge_source=judge_source,
            )
            state.facts.append(
                dict(kind="battle_context", id=context.id, body=context.model_dump_json())
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.battle_proposed",
                state,
                event_id=event,
                context=context.id,
                scene=cast.id,
            )
            return dict(id=context.id, state=context.state)

        return self.store._write(
            viewer,
            key,
            "m3.battle_proposed",
            dict(
                revision=revision,
                channel=channel,
                declaration=declaration.model_dump(mode="json"),
                parent=parent,
                **({"source_work": source_work} if source_work is not None else {}),
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: authorize(self.game, c, viewer),
        )

    def defenses(self, viewer: GuildViewer, identity: str) -> list[dict[str, Any]]:
        """Only pre-declaration actual NPC possessions, capability Tags and real cover."""
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            raw = next(
                (
                    x
                    for x in reversed(state.facts)
                    if x.get("kind") == "battle_context" and x.get("id") == identity
                ),
                None,
            )
            context = Context.model_validate_json(raw["body"]) if raw else None
            if context is None or viewer.user_id != context.adjudicator:
                raise WorkflowError("Only the actual source adjudicator reviews NPC defenses.")
            target = context.declaration.target
            if rules.category(state, target) != "npc":
                return []
            actual = resolve(state, target, profiles(c, self.store.campaign_id))
            if actual.cell is None:
                return []
            assert state.world is not None
            npc = next(x for x in state.world.npcs if x.id == target.entity)
            possible: list[tuple[str, str, str]] = []
            from girlframe.engine.m3_items import same_holder
            from girlframe.services.m3_items import prove_item

            for item in state.held_items:
                if (
                    not same_holder(state, item.holder, target)
                    or item.location_mode != "carried"
                    or item.condition == "ruined"
                ):
                    continue
                try:
                    prove_item(c, self.game, state, item.id)
                except WorkflowError:
                    continue
                possible.append(("item", item.id, "Held object: " + item.name))
            possible.extend(("capability", x.id, "Capability Tag: " + x.label) for x in npc.tags)
            possible.extend(
                ("cover", x.id, "Protective place: " + x.name)
                for x in state.world.locations
                if x.cell == actual.cell and x.condition != "destroyed"
            )
            proposed = c.scalar(
                sa.select(t.events.c.seq).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == context.proposed_event,
                )
            )
            histories = (
                c.execute(
                    sa.select(t.events.c.id, t.m2["m2_state_history"].c.body_json)
                    .join(
                        t.m2["m2_state_history"],
                        t.events.c.id == t.m2["m2_state_history"].c.event_id,
                    )
                    .where(
                        t.events.c.campaign_id == self.store.campaign_id, t.events.c.seq < proposed
                    )
                    .order_by(t.events.c.seq)
                ).all()
                if proposed is not None
                else []
            )
            result = []
            for kind, source, label in possible:
                for historical in histories:
                    value = Defense.model_validate(
                        dict(
                            target=target,
                            kind=kind,
                            source_id=source,
                            source_event=historical.id,
                            account="Actual source relevance still requires adjudication",
                        )
                    )
                    try:
                        self._defense(c, state, context, value)
                    except WorkflowError:
                        continue
                    result.append(
                        dict(
                            id=str(uuid5(NAMESPACE_URL, identity + ":" + kind + ":" + source)),
                            label=label,
                            value=value.model_dump(mode="json"),
                        )
                    )
                    break
            return result

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        *,
        opening: bool,
        reach: bool,
        outside_permission: bool,
        indirect: bool,
        evidence: str,
        defense: Defense | None = None,
        dormant_awakened: bool = False,
        dormant_close: bool = False,
        core_capability_confirmed: bool = False,
        actor_outside_frame: bool | None = None,
        target_outside_frame: bool | None = None,
        fuel_losses: tuple["LossSelection", ...] | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            if dormant_close and not dormant_awakened:
                raise WorkflowError(
                    "Use the independent close-contact Dormant Play when no awakening occurs."
                )
            state = load_state(c, self.store.campaign_id)
            raw = next(
                (
                    x
                    for x in reversed(state.facts)
                    if x.get("kind") == "battle_context" and x.get("id") == identity
                ),
                None,
            )
            if state.revision != revision or raw is None:
                raise WorkflowError("STALE_BATTLE: reopen the actual current declaration.")
            value = Context.model_validate_json(raw["body"])
            human, appointment = MedicalService(self.store)._handler(c)
            if (
                viewer.user_id != human
                or human != value.adjudicator
                or appointment != value.appointment
                or value.state != "proposed"
            ):
                raise WorkflowError(
                    "Only the actual appointed source adjudicator confirms these facts."
                )
            bound = profiles(c, self.store.campaign_id)
            acting = resolve(state, value.declaration.actor, bound, require_current_profile=False)
            target = resolve(state, value.declaration.target, bound, require_current_profile=False)
            if (
                rules.resource_sha(state, value.declaration.actor, bound)
                != value.declaration.actor_sha256
                or rules.resource_sha(state, value.declaration.target, bound)
                != value.declaration.target_sha256
                or acting.position_sha256 != value.actor_position
                or target.position_sha256 != value.target_position
            ):
                raise WorkflowError(
                    "STALE_BATTLE: actual bodies or resources changed before review."
                )
            event = str(uuid4())
            prior_dormant_wake = None
            if (
                value.declaration.target.kind == "gorgon"
                and state.world is not None
                and any(
                    x.id == value.declaration.target.entity and x.gorgon_class == "dormant"
                    for x in state.world.gorgons
                )
            ):
                from girlframe.services.m3_gorgon_dormant import awakened_source

                prior_dormant_wake = awakened_source(self.game, c, state, value.declaration.target)
            if dormant_awakened or dormant_close:
                if (
                    value.declaration.target.kind != "gorgon"
                    or state.world is None
                    or not any(
                        x.id == value.declaration.target.entity and x.gorgon_class == "dormant"
                        for x in state.world.gorgons
                    )
                ):
                    raise WorkflowError(
                        "Only this actual Dormant Gorgon's genuine awakening has this cost."
                    )
                if prior_dormant_wake is not None:
                    raise WorkflowError(
                        "This original Gorgon is already awake; use actual close-contact controls."
                    )
            if defense is not None:
                self._defense(c, state, value, defense)
            changed = Context.model_validate_json(
                value.model_copy(
                    update=dict(
                        state="confirmed",
                        confirmed_event=event,
                        opening=opening,
                        reach=reach,
                        outside_permission=outside_permission,
                        indirect=indirect,
                        evidence=evidence,
                        defense=defense,
                        dormant_awakened=dormant_awakened,
                        dormant_close=dormant_close,
                        core_capability_confirmed=core_capability_confirmed,
                        actor_outside_frame=actor_outside_frame,
                        target_outside_frame=target_outside_frame,
                    )
                ).model_dump_json()
            )
            from girlframe.services.m3_fuel_shortage import bind_battle, synchronize

            fuel_bound = bind_battle(self.game, c, state, changed, event, fuel_losses or ())
            if fuel_bound:
                channel = c.scalar(
                    sa.select(t.m2["m2_scenes"].c.channel_id).where(
                        t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_scenes"].c.id == changed.scene,
                    )
                )
                if channel is None:
                    raise WorkflowError("Recover the actual fuel-shortage battle scene")
                changed = changed.model_copy(
                    update={"cast_revision": _cast(self.game, c, state, int(channel)).revision}
                )
            state.facts.append(
                dict(kind="battle_context", id=identity, body=changed.model_dump_json())
            )
            fuel_audit: dict[str, Any] = {}
            if fuel_bound:
                fuel_audit["fuel_losses"] = [x.model_dump(mode="json") for x in fuel_losses or ()]
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.battle_confirmed",
                state,
                event_id=event,
                context=identity,
                source_event=value.proposed_event,
                **fuel_audit,
            )
            if fuel_bound:
                synchronize(self.game, c, event)
            return dict(id=identity, state=changed.state)

        return self.store._write(
            viewer,
            key,
            "m3.battle_confirmed",
            dict(
                revision=revision,
                id=identity,
                opening=opening,
                reach=reach,
                outside_permission=outside_permission,
                indirect=indirect,
                evidence=evidence,
                defense=defense.model_dump(mode="json") if defense else None,
                dormant_awakened=dormant_awakened,
                dormant_close=dormant_close,
                core_capability_confirmed=core_capability_confirmed,
                actor_outside_frame=actor_outside_frame,
                target_outside_frame=target_outside_frame,
            )
            | (
                {"fuel_losses": [x.model_dump(mode="json") for x in fuel_losses]}
                if fuel_losses
                else {}
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: authorize(self.game, c, viewer),
        )

    def _defense(self, c: Connection, state: GameState, context: Context, value: Defense) -> None:
        if (
            value.target != context.declaration.target
            or rules.category(state, value.target) != "npc"
        ):
            raise WorkflowError("An NPC defense belongs to this actual ordinary NPC target.")
        events = t.events
        source = c.execute(
            sa.select(events.c.seq).where(
                events.c.campaign_id == self.store.campaign_id, events.c.id == value.source_event
            )
        ).scalar()
        proposed = c.execute(
            sa.select(events.c.seq).where(
                events.c.campaign_id == self.store.campaign_id,
                events.c.id == context.proposed_event,
            )
        ).scalar()
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        if source is None or proposed is None or source >= proposed or original is None:
            raise WorkflowError(
                "Prove the actual defense existed before the original attack declaration."
            )
        for check in (original, state):
            npc = (
                next((x for x in check.world.npcs if x.id == value.target.entity and x.alive), None)
                if check.world
                else None
            )
            if npc is None:
                raise WorkflowError("Recover this actual NPC's original living body and defense.")
            if resolve(check, value.target, (), require_current_profile=False).cell is None:
                raise WorkflowError(
                    "An actually offstage NPC cannot defend from a cached map square."
                )
            if value.kind == "item":
                if not any(
                    x.id == value.source_id
                    and x.holder == value.target
                    and x.location_mode == "carried"
                    and x.condition == "intact"
                    for x in check.held_items
                ):
                    raise WorkflowError(
                        "This actual NPC must really hold the preexisting defense item."
                    )
            elif value.kind == "capability":
                if not any(x.id == value.source_id for x in npc.tags):
                    raise WorkflowError(
                        "Use an actual preexisting NPC capability Tag, not invented immunity."
                    )
            elif check.world is None or not any(
                x.id == value.source_id and x.cell == npc.cell and x.condition != "destroyed"
                for x in check.world.locations
                if check.world
            ):
                raise WorkflowError(
                    "The NPC must actually be at this existing protective location."
                )

    def expose(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        target: ActorRef,
        account: str,
        *,
        opponent: ActorRef | None = None,
        willing: bool = False,
        tag: str | None = None,
        scene: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_CORE: reopen the actual Frame facts.")
            bound = profiles(c, self.store.campaign_id)
            actual = resolve(state, target, bound, require_current_profile=False)
            human, appointment = MedicalService(self.store)._handler(c)
            if scene is not None:
                scenes = t.m2["m2_scenes"]
                channel = c.scalar(
                    sa.select(scenes.c.channel_id).where(
                        scenes.c.campaign_id == self.store.campaign_id,
                        scenes.c.id == scene,
                        scenes.c.open.is_(True),
                    )
                )
                if channel is None:
                    raise WorkflowError("STALE_CORE: reopen the actual original scene")
                cast = _cast(self.game, c, state, int(channel))
                if cast.id != scene:
                    raise WorkflowError("STALE_CORE: reopen the actual original scene")
                if not any(x.id == cast.id for x in state.scene_casts):
                    # This port proves actual legacy joins from immutable events.
                    # Persist that exact cast; no invented roles or controllers.
                    state.scene_casts.append(cast)
                _, human, _ = _scene_judge(self.game, c, state, cast)
            if willing:
                if viewer.user_id != actual.controller:
                    raise WorkflowError(
                        "Only the actual original Pilot willingly exposes her Frame."
                    )
            elif viewer.user_id != human:
                raise WorkflowError(
                    "The actual adjudicator confirms the real exposure circumstance."
                )
            event = str(uuid4())
            state = rules.expose_frame(
                state,
                target,
                bound,
                event,
                account,
                opponent=opponent,
                willing=willing,
                tag=tag,
                scene=scene,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.battle_frame_exposed",
                state,
                event_id=event,
                target=target.model_dump(mode="json"),
                willing=willing,
                appointment=appointment,
            )
            return dict(event=event, target=target.model_dump(mode="json"))

        command = dict(
            revision=revision,
            target=target.model_dump(mode="json"),
            opponent=opponent.model_dump(mode="json") if opponent else None,
            account=account,
            willing=willing,
            tag=tag,
        )
        if scene is not None:
            command["scene"] = scene
        return self.store._write(
            viewer,
            key,
            "m3.battle_frame_exposed",
            command,
            operation,
            auto_audit=False,
            authorize=lambda c: authorize(self.game, c, viewer),
        )


def damage_blast_resource(
    game: "GameService",
    c: Connection,
    state: GameState,
    *,
    drop: str,
    target: ActorRef,
    asset: str,
    event: str,
    occurrence: str,
) -> tuple[GameState, tuple[str, ...]]:
    """Mandatory actual nuclear source proof; a physical Frame is never a proxy actor."""
    from girlframe.services.m3_a_bomb import prove_drop

    source = prove_drop(game, c, state, drop)
    resource = next((x for x in source.resources if x.actor == target and x.event is None), None)
    if resource is None or asset not in resource.assets:
        raise WorkflowError("Prove the original blast resource and actual outstanding damage")
    if target.kind != "pilot":
        return damage_actor(
            game,
            c,
            state,
            target=target,
            asset_id=asset,
            source_action=None,
            source_work=drop,
            event=event,
            actor=source.handler,
            chooser_controller=resource.controller,
            occurrence="a_bomb:" + occurrence,
            physical_blow=False,
            indirect=True,
        )
    body = next((x for x in state.placements if x.actor == target), None)
    sheet = state.sheets.get(target.entity)
    if (
        body is None
        or sheet is None
        or sheet.character_id != target.incarnation
        or body.vessel_id != resource.vessel
        or body.frame_instance != resource.frame
        or body.frame_cell != resource.cell
    ):
        raise WorkflowError("Never damage a successor body or replacement Frame")
    if body.mode != "outside_frame":
        return damage_actor(
            game,
            c,
            state,
            target=target,
            asset_id=asset,
            source_action=None,
            source_work=drop,
            event=event,
            actor=source.handler,
            chooser_controller=resource.controller,
            occurrence="a_bomb:" + occurrence,
            physical_blow=False,
            indirect=True,
        )
    selected = next(
        (x for x in sheet.assets if x.id == asset and x.family == "frame" and not x.damaged), None
    )
    if selected is None:
        raise WorkflowError("Damage a real intact Asset of this independently placed Frame")
    changed = GameState.model_validate_json(state.model_dump_json())
    for actual in changed.sheets[target.entity].assets:
        if actual.id == asset:
            actual.damaged = True
    changed.sheets[target.entity].revision += 1
    changed.facts.append(
        dict(
            kind="a_bomb_vacant_frame_damage",
            drop=drop,
            event=event,
            target=target.model_dump_json(),
            frame=resource.frame or "",
            asset=asset,
        )
    )
    from girlframe.engine.m3_appearance_matrix import record_damage

    record_damage(
        state,
        changed,
        damager=source.handler,
        target=target,
        identity=asset,
        scene=None,
        event=event,
        action=None,
        work=drop,
        occurrence=occurrence,
    )
    return changed, ()
