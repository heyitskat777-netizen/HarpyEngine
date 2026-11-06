"""Actual battle effect ports; canonical staging precedes, SQL work follows the real event."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_battle as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
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
    for event, kind, human in (
        (value.proposed_event, "m3.battle_proposed", value.owner),
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


def prepare(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    scene: dict[str, Any],
    prepared: PlayInput,
) -> dict[str, Any]:
    authorize(game, c, viewer)
    if (
        prepared.target is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or prepared.source_work
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
    if prepared.parent != context.source_action:
        raise WorkflowError("Use this actual declaration's frozen original source parent.")
    if (
        context.state != "confirmed"
        or context.owner != viewer.user_id
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
    if acting.offstage_source is not None or target.offstage_source is not None:
        raise WorkflowError(
            "Resolve the actual offstage travel before declaring a battlefield attack."
        )
    if prepared.piloting != bool(acting.piloting):
        raise WorkflowError("Use the original body's actual piloting context for this battle.")
    if (
        acting.controller != viewer.user_id
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


def modifier(state: GameState, action: dict[str, Any]) -> int:
    return int(action["data"]["battle"]["modifier"])


def pre_roll(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
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
    for ref, old_sha in (
        (context.declaration.actor, context.declaration.actor_sha256),
        (context.declaration.target, context.declaration.target_sha256),
    ):
        if rules.resource_sha(state, ref, bound) != old_sha:
            raise WorkflowError("STALE_BATTLE: actual combat resources changed before dice.")
    from girlframe.engine.m3_budget_sabotage import matching as trapped_assets

    if trapped_assets(state, context.declaration.actor, {context.declaration.attacking_asset}):
        raise WorkflowError(
            "SOURCE_PORT_REQUIRED: resolve this battle Asset's sabotage before dice"
        )
    meta["roll_event"] = str(uuid4())
    state.facts.append(
        dict(
            kind="battle_context_used",
            context=context.id,
            action=action["id"],
            event=meta["roll_event"],
        )
    )


def _refs(action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    meta = action["data"]["battle"]
    return tuple(ActorRef.model_validate_json(json.dumps(meta[x])) for x in ("actor", "target"))  # type: ignore[return-value]


def results(game: "GameService", c: Connection, action: dict[str, Any]) -> None:
    from girlframe.services.m3_enforcer_firepower import results_firepower

    if results_firepower(game, c, action):
        return
    meta = action["data"]["battle"]
    level = action["data"]["result"]["tier"]
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
    bound = profiles(c, game.store.campaign_id)
    target_view = resolve(state, target, bound, require_current_profile=False)
    if any(x.id == asset_id and x.family == "girl" for x in target_view.assets):
        from girlframe.engine.m3_am import require_harm

        require_harm(state, actor, target)
    grant = next((x for x in state.handler_plays if x.id == source_work), None)
    if grant is not None:
        from girlframe.services.m3_handler_plays import validate_damage_source

        validate_damage_source(c, game, state, grant.id, target, actor, chooser_controller, event)
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
    return changed, tuple(ids)


def damage_frame_at_scene(
    game: "GameService",
    c: Connection,
    state: GameState,
    *,
    target: ActorRef,
    frame_instance: str,
    asset_id: str,
    source_action: str,
    event: str,
    actor: ActorRef,
    chooser_controller: int,
    occurrence: str,
) -> tuple[GameState, tuple[str, ...]]:
    """Actual Snoop damage to a proven current vacant Frame, never its absent Girl."""
    from girlframe.engine.m3_physical import occupied_frame
    from girlframe.services.m3_enforcer_snoop import validate_frame_damage_source

    validate_frame_damage_source(c, game, state, source_action, target, frame_instance, asset_id)
    if target.kind != "pilot":
        raise WorkflowError("The actual assigned Frame port requires its original Pilot owner.")
    bound = profiles(c, game.store.campaign_id)
    actual = resolve(state, target, bound, require_current_profile=False)
    if actual.frame_instance != frame_instance:
        raise WorkflowError(
            "The discovered Frame instance has changed; do not damage its replacement."
        )
    body = next((x for x in state.placements if x.actor == target), None)
    if body is None:
        raise WorkflowError("Record actual original cockpit occupancy before damaging this Frame.")
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
            source_work=None,
            event=event,
            actor=actor,
            chooser_controller=chooser_controller,
            occurrence=occurrence,
            physical_blow=False,
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
            source_action=source_action,
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
        scene=game.action(c, source_action)["scene_id"],
        event=event,
        action=source_action,
        work=None,
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
    if body.get("source_work"):
        from girlframe.services.m3_sprite import complete_children

        if complete_children(game, c, body["source_work"], event, viewer, key):
            return
    if any(x.id == body.get("source_work") for x in state.handler_plays):
        from girlframe.services.m3_handler_plays import complete_damage

        complete_damage(game, c, body["source_work"], event, viewer, key)
    if body.get("source_action"):
        action = game.action(c, body["source_action"])
        if action["data"].get("battle"):
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


def damage_prerequisites(game: "GameService", c: Connection, row: dict[str, Any]) -> None:
    from girlframe.services.m3_collateral import latest

    body = json.loads(row["body_json"])
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
            if value is None or viewer.user_id not in (value.owner, value.adjudicator):
                raise WorkflowError(
                    "This saved battle context belongs to its actual source humans."
                )
            channel = c.scalar(
                sa.select(t.m2["m2_scenes"].c.channel_id).where(
                    t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_scenes"].c.id == value.scene,
                )
            )
            return dict(
                context=value.model_dump(mode="json"),
                channel=int(channel) if channel else None,
                revision=state.revision,
            )

    def preview(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
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
            actors = []
            for role in cast.roles:
                if not _visible(state, role.actor, viewer.user_id):
                    continue
                actual = resolve(state, role.actor, bound, require_current_profile=False)
                if actual.controller != role.controller:
                    raise WorkflowError("Recover the actual scene controller assignment.")
                owned = actual.controller == viewer.user_id
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
                    if item.scene == cast.id and viewer.user_id in (item.owner, item.adjudicator):
                        contexts[item.id] = item
            return dict(
                revision=state.revision,
                channel=channel,
                scene=cast.id,
                actors=actors,
                contexts=[x.model_dump(mode="json") for x in contexts.values()],
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
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_BATTLE: reopen the actual scene declaration.")
            source_choice = None
            if parent:
                source = self.game.action(c, parent)
                request: dict[str, Any] | None
                if source["data"].get("gorgon_play"):
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
            if not _visible(state, declaration.target, viewer.user_id):
                raise WorkflowError(
                    "Reveal the actual target in Conversation before declaring this attack."
                )
            if (
                actor.controller != viewer.user_id
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
                if asset.concealed and target.controller != viewer.user_id:
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
                owner=viewer.user_id,
                adjudicator=handler,
                appointment=appointment,
                proposed_event=event,
                cast_revision=cast.revision,
                actor_position=actor.position_sha256,
                target_position=target.position_sha256,
                core_source=core,
                source_action=parent,
                source_choice=source_choice,
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
            state.facts.append(
                dict(kind="battle_context", id=identity, body=changed.model_dump_json())
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.battle_confirmed",
                state,
                event_id=event,
                context=identity,
                source_event=value.proposed_event,
            )
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
