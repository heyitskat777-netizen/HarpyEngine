"""Held actual-actor Engage, including source-owned damage and the Harpy extra maneuver."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_engage as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def prepare(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    scene: dict[str, Any],
    prepared: PlayInput,
    *,
    actor_ref: ActorRef | None = None,
) -> dict[str, Any]:
    from girlframe.services.m3_access import Access
    from girlframe.services.m3_battle import _cast, _scene_judge

    Access(game.store).authorize(c, viewer, "plays")
    cast = _cast(game, c, state, int(scene["channel_id"]))
    bound = profiles(c, game.store.campaign_id)
    actor_ref = actor_ref or ActorRef(
        kind="pilot",
        entity=str(viewer.user_id),
        incarnation=game.character_binding(c, state, viewer.user_id, require_current_profile=False),
    )
    target = prepared.target_actor
    if target is None or target == actor_ref:
        raise WorkflowError("Choose the actual opposing battlefield actor for Engage")
    acting, opposing = (resolve(state, ref, bound) for ref in (actor_ref, target))
    if acting.controller != viewer.user_id or not (
        acting.ref.kind == "pilot" or acting.ref.kind == "external_pilot" and acting.girl == "harpy"
    ):
        raise WorkflowError("Use this actual Pilot or Harpy's own battlefield resources")
    if not all(any(role.actor == ref for role in cast.roles) for ref in (actor_ref, target)):
        raise WorkflowError("Both actual battlefield actors must belong to this source scene")
    if acting.offstage_source or opposing.offstage_source:
        raise WorkflowError("An actual offstage body cannot enter this battlefield declaration")
    if not any(not asset.damaged for asset in acting.assets):
        raise WorkflowError("No actual undamaged owned Asset is available for Engage")
    judge, human, source = _scene_judge(game, c, state, cast)
    return dict(
        actor=actor_ref.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        actor_sha256=acting.source_sha256,
        target_sha256=opposing.source_sha256,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        judge=judge.model_dump(mode="json") if judge else None,
        judge_controller=human,
        judge_source=source,
        table=sorted(
            {role.controller for role in cast.roles}
            | ({cast.facilitator} if cast.facilitator else set())
        ),
        followups=[],
        applied=False,
    )


def pre_roll(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m3_battle import _cast

    meta = action["data"]["engage"]
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    current = _cast(game, c, state, int(action["channel_id"]))
    if current != cast or fingerprint(cast) != meta["cast_sha256"]:
        raise WorkflowError("STALE_CAST: recover the original battlefield declaration before dice")
    for key in ("actor", "target"):
        actual = resolve(
            state, ActorRef.model_validate(meta[key]), profiles(c, game.store.campaign_id)
        )
        if actual.source_sha256 != meta[key + "_sha256"]:
            raise WorkflowError("STALE_ENGAGE: actual battlefield resources changed before dice")


def results(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    game.request(c, action, int(action["actor_id"]), "engage_maneuvers")


def _actor(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> ActorRef:
    meta = action["data"].get("engage") or action["data"].get("battle")
    if meta is None:
        raise WorkflowError("Recover the actual source battlefield Play")
    return ActorRef.model_validate(meta["actor"])


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_battle import damage_actor

    extra = row["kind"] == "engage_assault_extra"
    if row["kind"] not in ("engage_maneuvers", "engage_assault_extra"):
        raise WorkflowError("Choose this actual source's pending maneuver response")
    meta = action["data"]["battle" if extra else "engage"]
    ref = _actor(game, c, state, action)
    actor = resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)
    if int(row["actor_id"]) != actor.controller or actor.controller != int(action["actor_id"]):
        raise WorkflowError("Only the actual acting body's human chooses its maneuvers")
    from girlframe.engine import m3_untouchable as untouchable
    from girlframe.services.m3_untouchable import entitlement

    selected_tag = answer.fields.get("untouchable_tag")
    receipt = None
    if selected_tag is not None:
        receipt = entitlement(game, c, state, ref)
        if receipt is None:
            raise WorkflowError("Acquire the actual current source-owned Untouchable Frame first")
    maneuver_answer = answer.model_copy(
        update={"fields": {k: v for k, v in answer.fields.items() if k != "untouchable_tag"}}
    )
    maneuvers, damage = rules.select(
        actor,
        action["data"]["result"]["tier"],
        maneuver_answer,
        assault_extra=extra,
        substitute_damage=selected_tag is not None,
    )
    if meta.get("extra_selected" if extra else "applied"):
        raise WorkflowError("This actual source maneuver choice has already resolved")
    from girlframe.services.m3_budget_sabotage import intercept as intercept_sabotage

    if intercept_sabotage(game, c, state, action, row, answer, ref, set(maneuvers.values())):
        return
    event = action["data"]["response_event"]
    if selected_tag is not None:
        assert receipt is not None
        untouchable.substitute(
            state,
            ref,
            selected_tag,
            action=action["id"],
            choice=row["id"],
            event=event,
            receipt=receipt,
        )
        action["data"]["result"]["untouchable_tag"] = selected_tag
    opponent = ActorRef.model_validate(meta["target"])
    executed = {
        k: v
        for k, v in maneuvers.items()
        if v not in action["data"].get("sabotage_failed_assets", [])
    }
    for kind, asset in executed.items():
        effect = rules.Maneuver.model_validate(
            dict(
                kind=kind,
                actor=ref,
                opponent=opponent,
                asset=asset,
                circumstances=answer.text.strip(),
                source_action=action["id"],
                source_event=event,
                scene=action["scene_id"],
            )
        )
        state.facts.append(dict(kind="engage_maneuver", body=effect.model_dump_json(), event=event))
    if extra:
        meta["extra_selected"] = True
        action["data"]["result"]["extra_maneuver"] = executed
        from girlframe.services.m3_battle import results as battle_results

        battle_results(game, c, action)
    else:
        meta["applied"] = True
        action["data"]["result"].update(maneuvers=executed, damaged=[damage] if damage else [])
        if damage:
            changed, required = damage_actor(
                game,
                c,
                state,
                target=ref,
                asset_id=damage,
                source_action=action["id"],
                source_work=None,
                event=event,
                actor=ref,
                opponent=opponent,
                chooser_controller=actor.controller,
                occurrence="engage_used_asset",
            )
            for name in GameState.model_fields:
                setattr(state, name, getattr(changed, name))
            meta["followups"].extend(required)


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    ref = _actor(game, c, state, action)
    actor = resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)
    extra = row["kind"] == "engage_assault_extra"
    from girlframe.services.m3_untouchable import tags as untouchable_tags

    substitutions = (
        untouchable_tags(game, c, state, ref)
        if not extra and action["data"]["result"]["tier"] != "mid"
        else []
    )
    count = 0 if extra else {"low": 1, "mid": 2, "high": 3}[action["data"]["result"]["tier"]]
    return dict(
        minimum=count,
        maximum=1 if extra else count + int(actor.girl == "harpy"),
        assets=[
            asset.model_dump(mode="json") | {"label": asset.name}
            for asset in actor.assets
            if not asset.damaged
        ],
        damage=not extra and action["data"]["result"]["tier"] != "mid",
        untouchable_tags=substitutions,
        opponent=(action["data"].get("engage") or action["data"]["battle"])["target"],
    )


def synchronize(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.services.m3_battle import synchronize_damage

    synchronize_damage(game, c, event)
    if action["data"]["engage"]["applied"] and not game.pending(c, action["id"]):
        state = load_state(c, game.store.campaign_id)
        if action["data"].get("actor_basic"):
            from girlframe.services.m3_actor_plays import ActorPlayService

            ActorPlayService(game).finish(c, state, action)
        else:
            from girlframe.services.m2_choices import ChoiceEngine

            ChoiceEngine(game).finish(c, state, action)
        game.save_action(c, action)


def complete_damage_work(
    game: "GameService",
    c: Connection,
    row: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    source = json.loads(row["body_json"]).get("source_action")
    if source:
        action = game.action(c, source)
        if action["data"].get("engage"):
            synchronize(game, c, action, event, viewer, key)


def start_assault_extra(game: "GameService", c: Connection, action: dict[str, Any]) -> None:
    """Ask before primary Assault effects; the same used Asset may subsequently be damaged."""
    meta = action["data"]["battle"]
    if meta.get("extra_started"):
        raise WorkflowError("Resume the existing actual Harpy extra-maneuver choice")
    meta["extra_started"] = True
    game.request(c, action, int(action["actor_id"]), "engage_assault_extra")


def ensure_assault_extra(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> bool:
    if action["data"]["play"] != "all_out_assault" or not action["data"].get("actor_basic"):
        return True
    ref = ActorRef.model_validate(action["data"]["actor_basic"]["ref"])
    if ref.kind != "external_pilot":
        return True
    if not action["data"]["battle"].get("extra_selected"):
        if game.pending(c, action["id"]):
            return False
        raise WorkflowError("Resolve the actual Harpy's extra maneuver before Assault consequences")
    return True
