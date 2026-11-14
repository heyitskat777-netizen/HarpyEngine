"""Printed no-dice Gorgon effects, real response Plays and concrete environmental outcomes."""

import json
from typing import Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_battle as battle
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_collateral import Selection, Source, perform
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_state import Asset
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _meta(action: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], action["data"]["gorgon_play"])


def _ref(value: Any) -> ActorRef:
    return ActorRef.model_validate(value)


def _event(action: dict[str, Any]) -> str:
    return str(action["data"]["response_event"])


def _request(
    game: Any, c: Connection, action: dict[str, Any], owner: int, kind: str, **body: Any
) -> str:
    return str(
        game.request(
            c,
            action,
            owner,
            "gorgon_" + kind,
            dict(
                actor=body.pop("actor", _meta(action).get("target")),
                attacker=_meta(action)["actor"],
                **body,
            ),
        )
    )


def _append(action: dict[str, Any], identities: tuple[str, ...]) -> None:
    followups = _meta(action).setdefault("followups", [])
    followups.extend(x for x in identities if x not in followups)


def _copy(destination: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(destination, field, getattr(source, field))


def _actor(state: GameState, action: dict[str, Any]) -> Any:
    assert state.world is not None
    return next(x for x in state.world.gorgons if x.id == _ref(_meta(action)["actor"]).entity)


def _one(answer: ChoiceAnswer, choices: tuple[str, ...]) -> str:
    if (
        len(answer.options) != 1
        or answer.options[0] not in choices
        or not answer.text.strip()
        or answer.denied
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Choose the actual source option and describe its concrete effect.")
    return answer.options[0]


def start(game: Any, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = _meta(action)
    if meta.get("runtime_started"):
        raise WorkflowError("This actual Gorgon intent already started its effects.")
    actual = _actor(state, action)
    if not actual.alive:
        raise WorkflowError("A dead original Gorgon cannot begin another attack.")
    meta.update(runtime_started=True, followups=[], effects=[])
    from girlframe.services.m3_gorgon_dormant import record_own_wake

    record_own_wake(game, c, state, action)
    if meta["kind"] == "warp":
        if not actual.exposed:
            raise WorkflowError("Warp charges an actually exposed Core.")
        _request(game, c, action, meta["controller"], "warp")
        return
    if meta["kind"] == "collateral":
        _request(game, c, action, meta["controller"], "collateral")
        return
    from girlframe.services.m3_gorgon_dormant import stage

    if stage(game, c, state, action):
        return
    _start_attack(game, c, state, action)


def _start_attack(game: Any, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = _meta(action)
    target = _ref(meta["target"])
    from girlframe.engine.m3_janus_pandora import require_can_harm

    require_can_harm(state, _ref(meta["actor"]), target)
    victim = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    category = battle.category(state, target)
    if category == "pilot" and target.kind != "pilot":
        raise WorkflowError("This actual external Pilot needs its own source resource/Defeat port.")
    if category in ("gorgon", "harpy"):
        _request(game, c, action, victim.controller, "contest_assets")
    elif category == "npc":
        meta["fatal_pending"] = True
    elif category == "handler" and victim.rules != "handler_girl":
        _damage(game, c, state, action, target, None, occurrence="gorgon_attack")
    else:
        if victim.inside_frame is None:
            raise WorkflowError("Record the attacked original body/cockpit facts first.")
        _request(game, c, action, victim.controller, "defend")


def resume_after_dormant(
    game: Any, c: Connection, state: GameState, action: dict[str, Any], identity: str, event: str
) -> None:
    from girlframe.services.m3_gorgon_dormant import paid_source

    meta = _meta(action)
    if meta.get("dormant_work") != identity:
        raise WorkflowError("Resume the original source attack that incurred this exact counter")
    paid = paid_source(game, c, action, identity)
    if meta.get("dormant_paid"):
        if meta["dormant_paid"] != paid:
            raise WorkflowError("This source continuation already has a different real payment")
        return
    meta.update(dormant_paid=paid, phase="active", dormant_continuation_event=event)
    _start_attack(game, c, state, action)


def _damage(
    game: Any,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorRef,
    asset: str | None,
    *,
    occurrence: str,
) -> None:
    from girlframe.services.m3_battle import damage_actor

    actor = _ref(_meta(action)["actor"])
    from girlframe.engine.m3_janus_pandora import require_can_harm

    require_can_harm(state, actor, target)
    changed, work = damage_actor(
        game,
        c,
        state,
        target=target,
        asset_id=asset,
        source_action=action["id"],
        source_work=None,
        event=_event(action),
        actor=actor,
        chooser_controller=_meta(action)["controller"],
        occurrence=occurrence,
        physical_blow=True,
    )
    _copy(state, changed)
    _append(action, work)


def _response(
    game: Any,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    actor: ActorRef,
    *,
    effect: int | None = None,
) -> None:
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if battle.category(state, actor) not in ("pilot", "harpy") and actual.rules != "handler_girl":
        raise WorkflowError("Only an actual Girl/Harpy with its own Plays takes this response.")
    _request(
        game,
        c,
        action,
        actual.controller,
        "response_play",
        actor=actor.model_dump(mode="json"),
        effect=effect,
    )


def _collateral_effect(
    game: Any,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    item: dict[str, Any],
    choice: str,
) -> None:
    meta = _meta(action)
    if item.get("resolved"):
        return
    kind = item["kind"]
    if kind == "structure":
        source = Source(
            id=action["id"] + ":" + str(item["index"]),
            action=action["id"],
            choice=choice,
            event=_event(action),
            actor=_ref(meta["actor"]),
            actor_controller=meta["controller"],
            judge=meta["judge"],
            appointment=meta["appointment"],
            handler=active_handler(state),
            gorgon_cause=True,
        )
        assert state.world is not None
        structure = next(x for x in state.world.locations if x.id == item["structure"])
        pinned_wreck = structure.condition == "destroyed" and any(
            x.ship == structure.id
            and x.threat == _ref(meta["actor"]).entity
            and x.released_event is None
            for x in state.world.ship_pins
        )
        if pinned_wreck:
            state.facts.append(
                dict(
                    kind="ship_wreck_dealt_with",
                    ship=structure.id,
                    actor=_ref(meta["actor"]).model_dump_json(),
                    event=_event(action),
                    action=action["id"],
                    choice=choice,
                    account=item["account"],
                )
            )
        else:
            changed, loss = perform(
                state,
                source,
                Selection(
                    structures=(item["structure"],), account=item["account"], reach=item["account"]
                ),
                _event(action),
            )
            _copy(state, changed)
            if loss is not None:
                meta.setdefault("losses", []).append(loss.id)
        from girlframe.engine.m3_ship_base import release_pin

        release_pin(state, _ref(meta["actor"]).entity, structure.id, _event(action), action["id"])
    elif kind == "civilians":
        if state.world is None:
            raise WorkflowError("Recover actual threatened civilians in this source World.")
        selected = set(item["civilians"])
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"alive": False}) if x.id in selected else x
                    for x in state.world.npcs
                )
            }
        )
        for npc in selected:
            _copy(
                state,
                battle.end_actor_casts(state, ActorRef(kind="npc", entity=npc), _event(action)),
            )
        state.facts.append(
            dict(
                kind="gorgon_civilians_killed",
                action=action["id"],
                event=_event(action),
                victims=json.dumps(sorted(selected)),
                account=item["account"],
            )
        )
    else:
        state.facts.append(
            dict(
                kind="gorgon_" + kind + "_altered",
                action=action["id"],
                event=_event(action),
                account=item["account"],
            )
        )
    item["resolved"] = _event(action)
    item["applied"] = _event(action)


def _schedule_effect(
    game: Any,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    item: dict[str, Any],
    choice: str,
) -> None:
    actual = _actor(state, action)
    if item["kind"] in ("structure", "civilians") and actual.gorgon_class != "directed":
        _request(game, c, action, _meta(action)["judge"], "interrupt", effect=item["index"])
    else:
        _collateral_effect(game, c, state, action, item, choice)


def apply(
    game: Any,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    meta, event = _meta(action), _event(action)
    body = json.loads(row["body_json"])
    kind = row["kind"].removeprefix("gorgon_")
    if kind == "defend":
        target = _ref(body["actor"])
        defensive_assets = battle.intact_assets(state, target, profiles(c, game.store.campaign_id))
        selected = _one(answer, ("play", "damage") if defensive_assets else ("play",))
        if selected == "play":
            _response(game, c, state, action, target)
        else:
            _request(game, c, action, int(row["actor_id"]), "damage_asset")
    elif kind == "damage_asset":
        asset = _one(
            answer,
            tuple(
                x.id
                for x in battle.intact_assets(
                    state, _ref(body["actor"]), profiles(c, game.store.campaign_id)
                )
            ),
        )
        _damage(game, c, state, action, _ref(body["actor"]), asset, occurrence=row["id"])
    elif kind == "contest_assets":
        target = _ref(meta["target"])
        available = {
            x.id for x in battle.assets(state, target, profiles(c, game.store.campaign_id))
        }
        if (
            not answer.options
            or not set(answer.options) <= available
            or not answer.text.strip()
            or answer.denied
            or answer.fields
            or answer.flag is not None
        ):
            raise WorkflowError("Pit the actual target-owned Assets against the declared attack.")
        meta["defending_assets"] = list(answer.options)
        _request(game, c, action, meta["judge"], "contest_judge")
    elif kind == "contest_judge":
        winner = _one(answer, ("attacker", "defender"))
        loser = _ref(meta["target"] if winner == "attacker" else meta["actor"])
        choices = meta["defending_assets"] if winner == "attacker" else meta["assets"]
        losing_asset = answer.fields.get("asset", "")
        if losing_asset not in choices:
            raise WorkflowError("The judge names the actual losing Asset from the pitted Assets.")
        if loser.kind == "gorgon":
            assert state.world is not None
            losing_body = next(x for x in state.world.gorgons if x.id == loser.entity)
            protected = losing_body.protected_asset is not None and any(
                x.id == losing_body.protected_asset and not x.damaged for x in losing_body.assets
            )
            if protected and answer.flag is not True:
                raise WorkflowError(
                    "The real Directed protector cannot be dealt with by direct attack; "
                    "the actual judge must confirm the concrete indirect approach."
                )
            if protected:
                meta["contest_indirect"] = dict(event=event, account=answer.text)
        _destroy(game, c, state, action, loser, losing_asset, row["id"])
        state.facts.append(
            dict(
                kind="gorgon_asset_contest",
                action=action["id"],
                event=event,
                winner=winner,
                loser=loser.model_dump_json(),
                asset=losing_asset,
                account=answer.text,
            )
        )
    elif kind == "collateral":
        meta["collateral_choice"] = row["id"]
        options = {"civilians", "structure", "electronics", "environment"}
        if not 1 <= len(answer.options) <= 2 or not set(answer.options) <= options:
            raise WorkflowError("Choose one or two printed collateral effects.")
        if not answer.text.strip():
            raise WorkflowError("State the concrete actual destructive reach and effect.")
        actual = _actor(state, action)
        assert state.world is not None
        for index, selected in enumerate(answer.options):
            item: dict[str, Any] = dict(index=index, kind=selected, account=answer.text)
            if selected == "structure":
                location = next(
                    (
                        x
                        for x in state.world.locations
                        if x.id == answer.fields.get("structure")
                        and (
                            x.condition != "destroyed"
                            or any(
                                p.ship == x.id
                                and p.threat == _ref(meta["actor"]).entity
                                and p.released_event is None
                                for p in state.world.ship_pins
                            )
                        )
                    ),
                    None,
                )
                if location is None:
                    raise WorkflowError("Choose an actual surviving structure.")
                item["structure"] = location.id
                item["reach_review"] = actual.cell is None or location.cell != actual.cell
            elif selected == "civilians":
                identifiers = answer.fields.get("civilians", "").split(",")
                civilians = [
                    x
                    for x in state.world.npcs
                    if x.id in identifiers
                    and x.alive
                    and "civilian" in x.jobs
                    and resolve(state, ActorRef(kind="npc", entity=x.id), ()).offstage_source
                    is None
                    and (actual.cell is None or x.cell == actual.cell)
                ]
                if not civilians or {x.id for x in civilians} != set(identifiers):
                    raise WorkflowError("Choose actual living co-present civilian NPCs.")
                item["civilians"] = identifiers
            meta["effects"].append(item)
            if item.get("reach_review") and meta["controller"] != meta["judge"]:
                _request(game, c, action, meta["judge"], "collateral_reach", effect=index)
            else:
                _schedule_effect(game, c, state, action, item, row["id"])
    elif kind == "collateral_reach":
        verdict = _one(answer, ("reached", "unreachable"))
        item = meta["effects"][body["effect"]]
        item["reach_account"] = answer.text
        item["reach_event"] = event
        if verdict == "reached":
            _schedule_effect(game, c, state, action, item, row["id"])
        else:
            item["resolved"] = event
            item["unreachable"] = True
    elif kind == "interrupt":
        selected = _one(answer, ("play", "allow"))
        item = meta["effects"][body["effect"]]
        if selected == "allow":
            _collateral_effect(game, c, state, action, item, row["id"])
        else:
            actor = _ref(json.loads(answer.fields.get("actor", "{}")))
            cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
            if not any(x.actor == actor for x in cast.roles):
                raise WorkflowError(
                    "Only an actual original scene Girl may volunteer a saving Play."
                )
            _response(game, c, state, action, actor, effect=body["effect"])
    elif kind == "attack_judge":
        verdict = _one(answer, ("lands",) if body.get("unavoidable") else ("averted", "lands"))
        if body.get("effect") is None:
            if verdict == "lands":
                target = _ref(meta["target"])
                actual = resolve(
                    state,
                    target,
                    profiles(c, game.store.campaign_id),
                    require_current_profile=False,
                )
                _request(game, c, action, actual.controller, "damage_asset")
        elif verdict == "lands":
            _collateral_effect(game, c, state, action, meta["effects"][body["effect"]], row["id"])
        else:
            meta["effects"][body["effect"]]["resolved"] = event
        state.facts.append(
            dict(
                kind="gorgon_response_adjudicated",
                action=action["id"],
                child=body["child"],
                event=event,
                verdict=verdict,
                account=answer.text,
            )
        )
    elif kind == "warp":
        actual = _actor(state, action)
        warp_options = ["escalate"]
        if any(x.damaged for x in actual.assets):
            warp_options.append("evolve")
        if actual.core_strike_failed:
            warp_options.append("protect")
        selected = _one(answer, tuple(warp_options))
        if not actual.exposed:
            raise WorkflowError("The actual Warp requires its exposed Core to remain exposed.")
        changed = actual
        if selected == "evolve":
            evolved_asset = Asset(
                id=str(uuid4()),
                name=answer.fields.get("name", ""),
                description=answer.fields.get("description", ""),
                family="gorgon",
            )
            changed = actual.model_copy(update={"assets": (*actual.assets, evolved_asset)})
        elif selected == "protect":
            changed = actual.model_copy(update={"exposed": False, "core_strike_failed": False})
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "gorgons": tuple(changed if x.id == actual.id else x for x in state.world.gorgons)
            }
        )
        state.facts.append(
            dict(
                kind="gorgon_warp_" + selected,
                action=action["id"],
                event=event,
                account=answer.text,
            )
        )
    else:
        raise WorkflowError("Resume the actual source-owned Gorgon continuation.")


def _destroy(
    game: Any,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorRef,
    asset_id: str,
    occurrence: str,
    *,
    allow_sprite: bool = True,
    source_work: str | None = None,
) -> tuple[str, ...]:
    from girlframe.engine.m3_battle_state import Required
    from girlframe.services.m3_sprite import defer

    meta, event = _meta(action), _event(action)
    actor = _ref(meta["actor"])
    opponent = _ref(meta["target"]) if target == actor else actor
    from girlframe.engine.m3_janus_pandora import require_can_harm

    require_can_harm(state, actor, target)
    available = battle.assets(state, target, profiles(c, game.store.campaign_id))
    selected = next((x for x in available if x.id == asset_id), None)
    if selected is None:
        raise WorkflowError("The losing Asset must still belong to the actual original body.")
    if allow_sprite:
        changed, work = defer(
            game,
            c,
            state,
            target=target,
            asset=asset_id,
            source_action=action["id"],
            source_work=source_work,
            event=event,
            opponent=opponent,
            chooser=meta["controller"],
            occurrence=occurrence,
            effect="destroy",
            indirect=bool(meta.get("contest_indirect")),
        )
        if work:
            _copy(state, changed)
            _append(action, work)
            return work
    state.facts.append(
        dict(
            kind="actual_asset_destroyed",
            actor=target.model_dump_json(),
            asset=asset_id,
            original=selected.model_dump_json(),
            event=event,
            source_action=action["id"],
        )
    )
    if target.kind == "gorgon":
        assert state.world is not None
        original = next(x for x in state.world.gorgons if x.id == target.entity)
        changed_gorgon = original.model_copy(
            update={
                "assets": tuple(x for x in original.assets if x.id != asset_id),
                "destroyed_assets": (
                    *original.destroyed_assets,
                    next(x for x in original.assets if x.id == asset_id),
                ),
            }
        )
        state.world = state.world.model_copy(
            update={
                "gorgons": tuple(
                    changed_gorgon if x.id == target.entity else x for x in state.world.gorgons
                )
            }
        )
        return ()
    if battle.category(state, target) != "harpy":
        raise WorkflowError("Printed Asset contests involve actual Gorgons or Harpies.")
    from girlframe.engine.m3_harpy_resources import destroy_asset

    _copy(state, destroy_asset(state, target, asset_id, event=event))
    family = selected.family
    remaining = battle.assets(state, target, profiles(c, game.store.campaign_id))
    obligation = None
    if (
        family == "frame"
        and not selected.damaged
        and not any(x.family == "frame" and not x.damaged for x in remaining)
    ):
        obligation = Required(kind="harpy_defeat", target=target, opponent=opponent, source_pdf=182)
    elif (
        family == "girl"
        and not selected.damaged
        and not any(x.family == "girl" and not x.damaged for x in remaining)
    ):
        actual = resolve(
            state, target, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if actual.inside_frame is False:
            from girlframe.engine.m3_actor_bonds import make_helpless

            _copy(state, make_helpless(state, target, opponent, event))
    if obligation is None:
        return ()
    identity = str(uuid4())
    state.facts.append(
        dict(
            kind="battle_damage_stage",
            id=identity,
            stamp=identity,
            event=event,
            source_action=action["id"],
            source_work=source_work or "",
            requirement=obligation.model_dump_json(),
            chooser=str(meta["controller"]),
        )
    )
    _append(action, (identity,))
    return (identity,)


def projection(
    game: Any, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    meta = _meta(action)
    body = json.loads(row["body_json"])
    kind = row["kind"].removeprefix("gorgon_")
    result: dict[str, Any] = dict(kind=kind, account=action["data"].get("context", ""))
    if kind == "dormant_void":
        result.update(work_id=body["work_id"], actor=body["actor"], source="actual_gorgon_dormant")
    elif kind == "defend":
        result["options"] = ["play"]
        if battle.intact_assets(state, _ref(body["actor"]), profiles(c, game.store.campaign_id)):
            result["options"].append("damage")
    elif kind in ("damage_asset", "contest_assets"):
        actor = _ref(body["actor"])
        resources = battle.assets(state, actor, profiles(c, game.store.campaign_id))
        result["assets"] = [
            x.model_dump(mode="json") for x in resources if kind != "damage_asset" or not x.damaged
        ]
    elif kind == "contest_judge":
        result.update(
            options=["attacker", "defender"],
            attacking_assets=meta["assets"],
            defending_assets=meta["defending_assets"],
            indirect_required=any(
                x.protected_asset is not None
                and any(asset.id == x.protected_asset and not asset.damaged for asset in x.assets)
                for x in state.world.gorgons
                if x.id in (_ref(meta["actor"]).entity, _ref(meta["target"]).entity)
            )
            if state.world
            else False,
        )
    elif kind == "collateral":
        assert state.world is not None
        actual = _actor(state, action)
        result.update(
            options=["civilians", "structure", "electronics", "environment"],
            minimum=1,
            maximum=2,
            structures=[
                dict(id=x.id, label=x.name)
                for x in state.world.locations
                if x.condition != "destroyed"
                or any(
                    p.ship == x.id and p.threat == actual.ref.entity and p.released_event is None
                    for p in state.world.ship_pins
                )
            ],
            civilians=[
                dict(id=x.id, label=x.name)
                for x in state.world.npcs
                if x.alive
                and "civilian" in x.jobs
                and (actual.cell is None or x.cell == actual.cell)
            ],
        )
    elif kind == "collateral_reach":
        result.update(options=["reached", "unreachable"], effect=meta["effects"][body["effect"]])
    elif kind == "interrupt":
        result.update(
            options=["play", "allow"],
            actors=[
                dict(
                    ref=x.actor.model_dump(mode="json"),
                    label=resolve(
                        state,
                        x.actor,
                        profiles(c, game.store.campaign_id),
                        require_current_profile=False,
                    ).label,
                )
                for x in SceneCast.model_validate_json(json.dumps(meta["cast"])).roles
                if x.actor.kind in ("pilot", "external_pilot")
            ],
        )
    elif kind == "attack_judge":
        result.update(options=["averted", "lands"], child=body["child"])
    elif kind == "warp":
        actual = _actor(state, action)
        result["options"] = (
            ["escalate"]
            + (["evolve"] if any(x.damaged for x in actual.assets) else [])
            + (["protect"] if actual.core_strike_failed else [])
        )
    return result


def complete_response(
    game: Any,
    c: Connection,
    parent: dict[str, Any],
    child: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    meta = _meta(parent)
    source = child["data"]["gorgon_counter_source"]
    choices = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == source["choice"],
                choices.c.action_id == parent["id"],
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != "gorgon_response_play":
        raise WorkflowError("Recover the actual original response opportunity.")
    if row["state"] != "pending":
        return
    body = json.loads(row["body_json"])
    c.execute(
        choices.update()
        .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == row["id"])
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    state = load_state(c, game.store.campaign_id)
    actor_alive = _actor(state, parent).alive
    enough = child["data"].get("result", {}).get("enough")
    if enough is None:
        enough = child["data"].get("actor_basic", {}).get("enough")
    if not actor_alive or enough is True:
        if body.get("effect") is not None:
            meta["effects"][body["effect"]]["resolved"] = event
    elif enough is False:
        if body.get("effect") is None:
            actual = resolve(
                state,
                _ref(meta["target"]),
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            )
            _request(game, c, parent, actual.controller, "damage_asset")
        else:
            consequence = str(uuid4())
            parent["data"]["response_event"] = consequence
            _collateral_effect(game, c, state, parent, meta["effects"][body["effect"]], row["id"])
            principal = c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            )
            index = c.scalar(
                sa.select(sa.func.max(t.events.c.event_index)).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
                )
            )
            if principal is None:
                raise WorkflowError("Recover the actual failed saving Play event.")
            game.event(
                c,
                viewer.user_id if viewer else principal,
                key,
                "m3.gorgon_failed_response_effect",
                state,
                event_id=consequence,
                event_index=index + 1 if index is not None else 0,
                source_event=event,
                action_id=parent["id"],
                child=child["id"],
            )
            event = consequence
    else:
        _request(
            game,
            c,
            parent,
            meta["judge"],
            "attack_judge",
            child=child["id"],
            effect=body.get("effect"),
        )
    meta.setdefault("responses", []).append(
        dict(
            child=child["id"],
            event=event,
            choice=row["id"],
            actor=body["actor"],
            actual_enough=enough,
        )
    )
    game.save_action(c, parent)


def synchronize(
    game: Any,
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> bool:
    from girlframe.engine.m3_collateral import loss
    from girlframe.services.m3_battle import synchronize_casts, synchronize_damage
    from girlframe.services.m3_collateral import latest
    from girlframe.services.m3_quadrant_loss import materialize_loss

    meta = _meta(action)
    if not meta.get("runtime_started"):
        return False
    from girlframe.services.m3_gorgon_dormant import materialize as materialize_dormant

    materialize_dormant(game, c, action, event)
    synchronize_damage(game, c, event)
    state = load_state(c, game.store.campaign_id)
    if not _actor(state, action).alive:
        actions = t.m2["m2_actions"]
        active_child = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == game.store.campaign_id,
                actions.c.parent_id == action["id"],
                actions.c.state.not_in(("complete", "aborted")),
            )
        )
        if active_child is None:
            choices = t.m2["m2_choices"]
            for pending in game.pending(c, action["id"]):
                if pending["kind"].startswith("gorgon_"):
                    c.execute(
                        choices.update()
                        .where(
                            choices.c.campaign_id == game.store.campaign_id,
                            choices.c.id == pending["id"],
                            choices.c.state == "pending",
                        )
                        .values(state="completed_original_ended", revision=choices.c.revision + 1)
                    )
            meta["original_gorgon_ended"] = event
            meta["fatal_pending"] = False
    for identity in meta.get("losses", ()):
        value = loss(state, identity)
        materialize_loss(game, c, value, value.source_event, source_action=action["id"])
    synchronize_casts(game, c, event)
    if meta.get("fatal_pending"):
        game.save_action(c, action)
        apply_fatal(game, c, action, event, viewer, key)
        action = game.action(c, action["id"])
        meta = _meta(action)
    game.save_action(c, action)
    ready = all(
        latest(game, c, identity)["state"] == "resolved" for identity in meta.get("followups", ())
    ) and not meta.get("fatal_pending")
    if ready and not game.pending(c, action["id"]) and meta["kind"] == "collateral":
        _city_success(game, c, action, event, viewer, key)
    return ready


def _city_success(
    game: Any,
    c: Connection,
    action: dict[str, Any],
    prior: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    """One actual successful Play, not each selected effect, advances its printed City threat."""
    from girlframe.engine.m3_world import collateral_city

    meta = _meta(action)
    if meta.get("city_counted"):
        return
    state = load_state(c, game.store.campaign_id)
    actual = _actor(state, action)
    if actual.collateral_city is None or actual.collateral_resolved:
        return
    if not actual.alive:
        meta["city_counted"] = dict(source=prior, success=False, original_ended=True)
        game.save_action(c, action)
        return
    if resolve(state, _ref(meta["actor"]), ()).offstage_source:
        meta["city_counted"] = dict(source=prior, success=False, actual_offstage=True)
        game.save_action(c, action)
        return
    assert state.world is not None
    success = any(x.get("applied") for x in meta["effects"])
    result = collateral_city(state.world, actual.id, intercepted=not success)
    changed = next(x for x in result.world.gorgons if x.id == actual.id)
    if changed.collateral_successes == actual.collateral_successes:
        meta["city_counted"] = dict(source=prior, success=False)
        game.save_action(c, action)
        return
    event = str(uuid4())
    state.world = state.world.model_copy(update={"gorgons": result.world.gorgons})
    city = next(x for x in state.world.locations if x.id == actual.collateral_city)
    if changed.collateral_resolved and city.condition != "destroyed":
        source = Source(
            id=action["id"] + ":city",
            action=action["id"],
            choice=meta["collateral_choice"],
            event=event,
            actor=_ref(meta["actor"]),
            actor_controller=meta["controller"],
            judge=meta["judge"],
            appointment=meta["appointment"],
            handler=active_handler(state),
            gorgon_cause=True,
        )
        account = (
            "This actual City collapses after the source Gorgon's second successful Collateral Play"
        )
        state, _ = perform(
            state,
            source,
            Selection(
                structures=(city.id,),
                account=account,
                reach="The source Gorgon is actually at this threatened City",
            ),
            event,
        )
        state.facts.append(
            dict(
                kind="city_population_casualties",
                city=city.id,
                source_action=action["id"],
                source_event=event,
                population="many residents",
                account=(
                    "Actual City destruction kills many residents; "
                    "individual casualties unconfirmed"
                ),
            )
        )
    state.facts.append(
        dict(
            kind="gorgon_city_collateral_counted",
            source_action=action["id"],
            source_event=event,
            gorgon=actual.id,
            city=city.id,
            successes=str(changed.collateral_successes),
        )
    )
    meta["city_counted"] = dict(source=event, success=True)
    game.save_action(c, action)
    principal = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == prior
        )
    )
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    if principal is None:
        raise WorkflowError("Recover the actual completed Collateral Play's source event.")
    game.event(
        c,
        viewer.user_id if viewer else principal,
        key,
        "m3.gorgon_city_collateral_counted",
        state,
        event_id=event,
        event_index=index + 1 if index is not None else 0,
        source_event=prior,
        action_id=action["id"],
        gorgon=actual.id,
        city=city.id,
    )


def apply_fatal(
    game: Any,
    c: Connection,
    action: dict[str, Any],
    source_event: str,
    viewer: GuildViewer | None,
    key: str,
    *,
    allow_sprite: bool = True,
) -> None:
    from girlframe.engine.m3_physical import interrupt_journeys
    from girlframe.services.m3_battle import synchronize_casts, synchronize_damage
    from girlframe.services.m3_sprite import defer

    meta = _meta(action)
    if meta.get("fatal_event") or meta.get("fatal_intercepted") or meta.get("fatal_prevented"):
        return
    state = load_state(c, game.store.campaign_id)
    target = _ref(meta["target"])
    if target.kind != "npc" or battle.category(state, target) != "npc":
        raise WorkflowError("This printed automatic kill is for its actual ordinary NPC target.")
    actual = resolve(state, target, (), require_current_profile=False, require_alive=False)
    if not actual.alive:
        meta["fatal_pending"] = False
        game.save_action(c, action)
        return
    event = str(uuid4())
    if allow_sprite:
        changed, work = defer(
            game,
            c,
            state,
            target=target,
            asset=None,
            source_action=action["id"],
            source_work=None,
            event=event,
            opponent=_ref(meta["actor"]),
            chooser=meta["controller"],
            occurrence="gorgon_npc_kill",
            effect="fatal",
        )
        if work:
            _append(action, work)
            meta["fatal_pending"] = False
            state = changed
        else:
            allow_sprite = False
    if not allow_sprite:
        from girlframe.engine.m3_doctor import prevent_death

        state, prevented = prevent_death(state, target, event)
        if prevented:
            meta.update(fatal_pending=False, fatal_prevented=event)
        else:
            state = interrupt_journeys(state, target, event, "Actual Gorgon Attack kills this NPC.")
            state = battle.end_actor_casts(state, target, event)
            assert state.world is not None
            state.world = state.world.model_copy(
                update={
                    "npcs": tuple(
                        x.model_copy(update={"alive": False}) if x.id == target.entity else x
                        for x in state.world.npcs
                    )
                }
            )
            meta.update(fatal_pending=False, fatal_event=event)
        state.facts.append(
            dict(
                kind="gorgon_attack_npc_kept_alive" if prevented else "gorgon_attack_npc_killed",
                action=action["id"],
                event=event,
                target=target.model_dump_json(),
            )
        )
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    principal = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == source_event
        )
    )
    if principal is None:
        raise WorkflowError("Recover the actual source event of this automatic Gorgon effect.")
    game.save_action(c, action)
    game.event(
        c,
        viewer.user_id if viewer else principal,
        key,
        "m3.gorgon_attack_fatal_effect",
        state,
        event_id=event,
        event_index=index + 1 if index is not None else 0,
        source_event=source_event,
        action_id=action["id"],
    )
    synchronize_damage(game, c, event)
    synchronize_casts(game, c, event)
