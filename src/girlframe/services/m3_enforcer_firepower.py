"""An optional actual second enemy Asset hit stays inside its original Assault root."""

import json
from typing import Any, cast

from sqlalchemy import Connection

from girlframe.engine import m3_battle as battle
from girlframe.engine import m3_enforcer_requisitions as acquired
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_enforcer_requisitions import FIREPOWER
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcer_requisitions import owned, proof
from girlframe.services.onboarding import WorkflowError

KINDS = ("enforcer_firepower", "enforcer_firepower_context", "enforcer_firepower_confirm")


def prepare_firepower(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    cast: SceneCast,
    prepared: PlayInput,
) -> dict[str, Any] | None:
    if prepared.play != "all_out_assault":
        return None
    grant = owned(c, game, state, actor, FIREPOWER)
    return (
        dict(
            grant=grant.id,
            actor=actor.model_dump(mode="json"),
            cast=cast.model_dump(mode="json"),
            state="unrolled",
            rejected=[],
        )
        if grant
        else None
    )


def _meta(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any]:
    meta = action["data"].get("battle", {}).get("firepower")
    if (
        not meta
        or action["data"]["play"] != "all_out_assault"
        or action["data"]["result"]["tier"] != "high"
    ):
        raise WorkflowError("Overwhelming Firepower belongs only to this actual high Assault.")
    actor = ActorRef.model_validate(meta["actor"])
    grant = next((x for x in acquired.grants(state) if x.id == meta["grant"]), None)
    if grant is None or grant.rule != FIREPOWER:
        raise WorkflowError("Recover the actual original acquired Firepower source.")
    if grant.actor != actor:
        from girlframe.services.m3_tag_permissions import prove_birth

        body = next((x for x in state.harpy_states if x.id == actor.entity and x.alive), None)
        if (
            actor.kind != "external_pilot"
            or body is None
            or body.origin != grant.actor
            or FIREPOWER not in body.plays
        ):
            raise WorkflowError("Recover the actual explicitly retained original Firepower owner.")
        prove_birth(c, game, state, actor)
    proof(c, game, grant)
    return cast(dict[str, Any], meta)


def _targets(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> list[dict[str, Any]]:
    from girlframe.services.m3_battle import _visible

    meta = _meta(game, c, state, action)
    source = action["data"]["battle"]
    actor = ActorRef.model_validate(meta["actor"])
    if acquired.held(state, actor, FIREPOWER) is None:
        return []
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    bound = profiles(c, game.store.campaign_id)
    result = []
    for role in cast.roles:
        target = role.actor
        if target == actor or not _visible(state, target, int(action["actor_id"])):
            continue
        try:
            actual = resolve(state, target, bound, require_current_profile=False)
            from girlframe.engine.m3_items import same_holder
            from girlframe.services.m3_items import prove_item

            for item in state.held_items:
                if same_holder(state, item.holder, target) and item.asset_json is not None:
                    prove_item(c, game, state, item.id)
            possible = battle.intact_assets(state, target, bound)
        except ValueError:
            continue
        if not actual.alive:
            continue
        legal = [
            dict(id=x.id, label=x.name)
            for x in possible
            if not (
                target.model_dump(mode="json") == source["target"]
                and x.id == source["target_asset"]
            )
            and target.token + ":" + x.id not in meta["rejected"]
        ]
        if legal:
            result.append(
                dict(
                    ref=target.model_dump(mode="json"),
                    token=target.token,
                    label=actual.label,
                    controller=actual.controller,
                    assets=legal,
                )
            )
    return result


def results_firepower(game: GameService, c: Connection, action: dict[str, Any]) -> bool:
    meta = action["data"].get("battle", {}).get("firepower")
    if meta is None:
        return False
    if meta["state"] != "unrolled":
        return meta["state"] in ("choosing", "context", "confirmation")
    if action["data"]["result"]["tier"] != "high":
        meta["state"] = "inapplicable_tier"
        return False
    state = load_state(c, game.store.campaign_id)
    _meta(game, c, state, action)
    meta["state"] = "choosing"
    game.request(c, action, int(action["actor_id"]), KINDS[0])
    return True


def projection(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    meta = _meta(game, c, state, action)
    return dict(
        kind=request["kind"],
        targets=_targets(game, c, state, action) if request["kind"] == KINDS[0] else [],
        proposal=meta.get("proposal"),
    )


def _confirm(game: GameService, c: Connection, action: dict[str, Any]) -> None:
    meta = action["data"]["battle"]["firepower"]
    meta["state"] = "confirmation"
    game.request(c, action, action["data"]["battle"]["handler"], KINDS[2])


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_battle import damage_actor
    from girlframe.services.m3_battle import results as continue_primary

    meta = _meta(game, c, state, action)
    kind = request["kind"]
    if kind == KINDS[0]:
        if (
            meta["state"] != "choosing"
            or request["actor_id"] != str(action["actor_id"])
            or answer.flag is None
        ):
            raise WorkflowError(
                "The original acting owner chooses or declines its actual extra hit."
            )
        if not answer.flag:
            if answer.fields or answer.options or answer.denied or answer.number is not None:
                raise WorkflowError("Decline only this optional second hit.")
            meta["state"] = "declined"
            continue_primary(game, c, action)
            return
        if (
            set(answer.fields) != {"target", "asset"}
            or not answer.text.strip()
            or answer.options
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError(
                "Choose the actual second enemy and Asset and describe the extra hit."
            )
        if owned(c, game, state, ActorRef.model_validate(meta["actor"]), FIREPOWER) is None:
            raise WorkflowError("Recover the actual currently held extra-hit ability first.")
        candidate = next(
            (x for x in _targets(game, c, state, action) if x["token"] == answer.fields["target"]),
            None,
        )
        if candidate is None or answer.fields["asset"] not in {
            x["id"] for x in candidate["assets"]
        }:
            raise WorkflowError("Reopen the actual current second enemy Asset choices.")
        ref = ActorRef.model_validate(candidate["ref"])
        meta["proposal"] = dict(
            target=candidate["ref"],
            asset=answer.fields["asset"],
            account=answer.text,
            source=action["data"]["response_event"],
        )
        actual = resolve(
            state, ref, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        remaining = [
            x
            for x in battle.intact_assets(state, ref, profiles(c, game.store.campaign_id))
            if x.family == "girl"
        ]
        if actual.inside_frame is None and actual.rules == "handler_girl" and len(remaining) == 1:
            meta["state"] = "context"
            game.request(c, action, actual.controller, KINDS[1])
        else:
            _confirm(game, c, action)
        return
    proposal = meta.get("proposal")
    if not proposal:
        raise WorkflowError("Keep the exact original proposed second hit.")
    target = ActorRef.model_validate(proposal["target"])
    if kind == KINDS[1]:
        actual = resolve(
            state, target, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if (
            meta["state"] != "context"
            or int(request["actor_id"]) != actual.controller
            or answer.flag is None
            or not answer.text.strip()
            or answer.fields
            or answer.options
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError(
                "The actual original body owner records its factual inside/outside context."
            )
        action["data"]["battle"].setdefault("occupancy", {})[target.token] = answer.flag
        state.facts.append(
            dict(
                kind="enforcer_firepower_body_context",
                action=action["id"],
                target=target.model_dump_json(),
                inside=str(answer.flag).lower(),
                event=action["data"]["response_event"],
                account=answer.text,
            )
        )
        _confirm(game, c, action)
        return
    if (
        kind != KINDS[2]
        or meta["state"] != "confirmation"
        or int(request["actor_id"]) != action["data"]["battle"]["handler"]
        or answer.flag is None
        or not answer.text.strip()
        or answer.fields
        or answer.options
        or answer.denied
        or answer.number is not None
    ):
        raise WorkflowError("The actual frozen source judge confirms enemy/reach/relevance facts.")
    actor = ActorRef.model_validate(meta["actor"])
    if not answer.flag:
        meta["rejected"].append(target.token + ":" + proposal["asset"])
        meta.setdefault("rejections", []).append(proposal | dict(account=answer.text))
        meta["state"] = "choosing"
        game.request(c, action, int(action["actor_id"]), KINDS[0])
        return
    if owned(c, game, state, actor, FIREPOWER) is None:
        raise WorkflowError("Recover the actual currently held extra-hit ability first.")
    selected = next(
        (x for x in _targets(game, c, state, action) if x["ref"] == proposal["target"]), None
    )
    if selected is None or proposal["asset"] not in {x["id"] for x in selected["assets"]}:
        raise WorkflowError("The actual proposed second Asset changed; recover this source choice.")
    changed, followups = damage_actor(
        game,
        c,
        state,
        target=target,
        asset_id=proposal["asset"],
        source_action=action["id"],
        source_work=None,
        event=action["data"]["response_event"],
        actor=actor,
        chooser_controller=int(action["actor_id"]),
        occurrence="enforcer_firepower",
        indirect=False,
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    action["data"]["battle"]["followups"].extend(followups)
    meta["state"] = "applied"
    meta["effect_event"] = action["data"]["response_event"]
    meta["judge_account"] = answer.text
    continue_primary(game, c, action)
