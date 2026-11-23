"""Source-owned Harpy/Core ↔ Girl Beneath; no controller sheet or invented Status."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_beneath as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, Obligation, PlayInput, higher, shift_status
from girlframe.engine.m3_actor_bonds import change, depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_flirt import copy_state
from girlframe.engine.m3_role_punishment_state import RolePunishment
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_harpy_flirt import finish
from girlframe.services.onboarding import WorkflowError


def _present(actor: ActorView, target: ActorView) -> bool:
    return (
        actor.cell is not None
        and actor.cell == target.cell
        and not actor.offstage_source
        and not target.offstage_source
    )


def harpy_targets(actor: ActorView, cast: tuple[ActorView, ...]) -> tuple[ActorView, ...]:
    """Target choices for the same original Harpy and Girl checked by the native Play."""
    return tuple(
        target for target in cast if target.ref.kind == "pilot" and _present(actor, target)
    )


def prepare(
    game: GameService,
    c: Connection,
    state: GameState,
    cast: SceneCast,
    ref: ActorRef,
    prepared: PlayInput,
) -> dict[str, Any]:
    from girlframe.engine.m3_harpy_bond_void import is_harpy

    bound = profiles(c, game.store.campaign_id)
    actor = resolve(state, ref, bound)
    target = resolve(state, prepared.target_actor, bound) if prepared.target_actor else None
    if target is None or not (
        is_harpy(state, ref)
        and target.ref.kind == "pilot"
        or ref.kind == "pilot"
        and is_harpy(state, target.ref)
    ):
        raise WorkflowError("Choose the actual source-admitted Harpy/Core and original Girl")
    if prepared.play != rules.PLAY or prepared.target is not None or prepared.source_work:
        raise WorkflowError("Use this actual ordinary Beneath source without another work item")
    if not all(any(x.actor == v.ref for x in cast.roles) for v in (actor, target)):
        raise WorkflowError("Join both actual original people to this scene first")
    if not _present(actor, target):
        raise WorkflowError("Establish actual interaction between these original people")
    return dict(
        actor=ref.model_dump(mode="json"),
        target=target.ref.model_dump(mode="json"),
        actor_controller=actor.controller,
        target_controller=target.controller,
        cast=cast.model_dump(mode="json"),
    )


def validate(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any]:
    meta = action["data"][rules.MARKER]
    for key in ("actor", "target"):
        actor = ActorRef.model_validate(meta[key])
        actual = resolve(
            state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if actual.controller != meta[key + "_controller"]:
            raise WorkflowError("Recover the actual original Beneath response owner")
    return dict(meta)


def actual(game: GameService, c: Connection, state: GameState, ref: ActorRef) -> ActorView:
    return resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)


def bonds(
    game: GameService, c: Connection, state: GameState, victim: ActorRef
) -> list[dict[str, Any]]:
    from girlframe.engine.m3_actor_bonds import current_ref

    peers = {
        p
        for edge in state.actor_bonds
        for p in (edge.first, edge.second)
        if victim in (edge.first, edge.second) and p != victim
    }
    peers.update(
        current_ref(state, uid) for uid in (*state.order, state.handler) if uid is not None
    )
    if state.world:
        peers.update(ActorRef(kind="npc", entity=x.id) for x in state.world.npcs)
    result: list[dict[str, Any]] = []
    for peer in sorted(peers, key=lambda x: x.token):
        if peer == victim or depth(state, victim, peer) < 1:
            continue
        view = resolve(
            state,
            peer,
            profiles(c, game.store.campaign_id),
            require_alive=False,
            require_current_profile=False,
        )
        result.append(dict(token=peer.token, ref=peer.model_dump(mode="json"), label=view.label))
    return result


def options(
    game: GameService,
    c: Connection,
    state: GameState,
    setter: ActorRef,
    victim: ActorRef,
    level: str,
) -> dict[str, Any]:
    base = ["tag"]
    if rules.status_applicable(victim):
        base.append("status")
    if bonds(game, c, state, victim):
        base.append("bond")
    extra = ["lock_tag", "pin"]
    if setter.kind == "external_pilot" and victim.kind == "pilot":
        extra.append("punish")
    return dict(
        base=base,
        extra=extra,
        damage=level == "low",
        status_note="Harpies and Rebels exist outside the Status system (book PDF195)",
        punishment_note="Punishment requires the actual superior issuer to confirm her real order",
        issuers=order_issuers(game, c, state, victim) if "punish" in extra else [],
    )


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    validate(game, c, state, action)
    setter, _ = rules.roles(action, action["data"]["result"]["tier"])
    game.request(c, action, actual(game, c, state, setter).controller, "harpy_beneath_select")


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    from girlframe.engine.m3_mockingbird import actor_tags

    validate(game, c, state, action)
    level = action["data"]["result"]["tier"]
    setter, victim = rules.roles(action, level)
    view = actual(game, c, state, victim)
    setter_view = actual(game, c, state, setter)
    data = dict(
        affected_label=view.label,
        maximum=1 if level == "low" else 2,
        **options(game, c, state, setter, victim, level),
    )
    if row["kind"] == "harpy_beneath_select":
        data["tags"] = [
            dict(id=x.id, label=x.label)
            for x in actor_tags(state, victim)
            if setter_view.controller in getattr(x, "observers", ())
        ]
    if row["kind"] == "harpy_beneath_details":
        body = json.loads(row["body_json"])
        data.update(
            options=body["options"],
            bonds=bonds(game, c, state, victim),
            assets=[x.model_dump(mode="json") for x in view.assets if not x.damaged],
        )
    if row["kind"] == "harpy_beneath_order_confirmation":
        body = json.loads(row["body_json"])
        data.update(
            order=body["instruction"],
            recipient=setter_view.label,
            target=view.label,
            issuer=actual(game, c, state, ActorRef.model_validate(body["issuer"])).label,
        )
    return data


def _apply_effects(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    selected: ChoiceAnswer,
    peer: ActorRef | None = None,
    asset: str | None = None,
) -> None:
    from girlframe.engine.m3_mockingbird import actor_tags, give_tag

    event = action["data"]["response_event"]
    level = action["data"]["result"]["tier"]
    setter, victim = rules.roles(action, level)
    owner, target = actual(game, c, state, setter), actual(game, c, state, victim)
    choice = json.loads(request["body_json"]).get("source_choice", request["id"])
    chosen = selected.options
    if "status" in chosen:
        if not rules.status_applicable(victim):
            raise WorkflowError("Harpies have no Foundation Status to lower")
        shift_status(state, int(victim.entity), -1)
    new_tag = action["id"] + ":harpy-beneath-tag:" + choice
    if "tag" in chosen:
        copy_state(
            state,
            give_tag(
                state,
                profiles(c, game.store.campaign_id),
                victim,
                setter,
                selected.fields["tag"],
                new_tag,
                event,
                tuple(action["data"]["participants"]),
            ),
        )
    if "bond" in chosen:
        if peer is None or depth(state, victim, peer) < 1:
            raise WorkflowError("Choose the original affected person's actual existing Bond")
        copy_state(state, change(state, victim, peer, -1, event))
    if "lock_tag" in chosen:
        identity = selected.fields["locked_tag"]
        identity = new_tag if identity == "new" and "tag" in chosen else identity
        tag = next((x for x in actor_tags(state, victim) if x.id == identity), None)
        if tag is None or owner.controller not in getattr(tag, "observers", ()):
            raise WorkflowError("Choose only this decision owner's actual known Tag")
        gate = rules.lock(
            state,
            action=action["id"],
            choice=choice,
            setter=setter,
            victim=victim,
            setter_owner=owner.controller,
            victim_owner=target.controller,
            tag=tag.id,
            label=tag.label,
        )
        gate.details["effect_choice"] = request["id"]
    if "pin" in chosen:
        game.request(
            c,
            action,
            target.controller,
            "harpy_beneath_pin_response",
            dict(actor=victim.model_dump(mode="json"), attacker=setter.model_dump(mode="json")),
        )
        state.facts.append(
            dict(
                kind="harpy_physical_pin",
                action=action["id"],
                setter=setter.model_dump_json(),
                victim=victim.model_dump_json(),
                event=event,
                account=selected.text,
            )
        )
    if "punish" in chosen:
        from girlframe.services.m3_role_punishments import open_case

        authority = action["data"][rules.MARKER].get("authority")
        prove_authority(game, c, state, action, authority, pending=True)
        identity = action["id"] + ":harpy-beneath-punishment:" + choice
        changed, case = open_case(
            state,
            profiles(c, game.store.campaign_id),
            actor=setter,
            target=victim,
            chooser=setter,
            source_kind="harpy_beneath",
            source_event=event,
            action=action["id"],
            identity=identity,
        )
        copy_state(state, changed)
        game.request(c, action, owner.controller, "harpy_beneath_punishment", dict(case=case))
        action["data"][rules.MARKER]["punishment"] = case
    if "damage" in chosen:
        from girlframe.services.m3_battle import damage_actor

        changed, work = damage_actor(
            game,
            c,
            state,
            target=victim,
            asset_id=asset,
            source_action=action["id"],
            source_work=None,
            event=event,
            actor=setter,
            opponent=setter,
            occurrence="harpy-beneath-counter",
        )
        copy_state(state, changed)
        action["data"][rules.MARKER]["damage_followups"] = list(work)
    rules.record(state, action["id"], choice, setter, victim, chosen, event, selected.text)
    action["data"]["result"]["beneath_effects"] = list(chosen)
    if not game.pending(c, action["id"]):
        # Damage may still create its source-proved mandatory children after audit.
        if not action["data"][rules.MARKER].get("damage_followups"):
            finish(game, c, state, action)


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    validate(game, c, state, action)
    kind, level = request["kind"], action["data"]["result"]["tier"]
    setter, victim = rules.roles(action, level)
    if kind == "harpy_beneath_order_confirmation":
        body = json.loads(request["body_json"])
        issuer = ActorRef.model_validate(body["issuer"])
        if (
            request["actor_id"] != str(actual(game, c, state, issuer).controller)
            or answer.flag is None
            or not answer.text.strip()
            or answer.options
            or answer.denied
            or answer.fields
            or answer.member is not None
            or answer.number is not None
        ):
            raise WorkflowError("Only the actual issuing superior confirms this exact real order")
        if not answer.flag:
            game.request(
                c, action, actual(game, c, state, setter).controller, "harpy_beneath_select"
            )
            action["data"]["result"]["declined_order"] = answer.text
            return
        authority = dict(
            issuer=body["issuer"],
            recipient=setter.model_dump(mode="json"),
            target=victim.model_dump(mode="json"),
            instruction=body["instruction"],
            source_action=action["id"],
            choice=request["id"],
            event=action["data"]["response_event"],
            issuer_account=answer.text,
        )
        prove_authority(game, c, state, action, authority, pending=True)
        state.facts.append(
            dict(
                kind="harpy_beneath_order",
                action=action["id"],
                body=json.dumps(authority, sort_keys=True),
            )
        )
        action["data"][rules.MARKER]["authority"] = authority
        original = dict(request, body_json=json.dumps(dict(source_choice=body["source_choice"])))
        _apply_effects(
            game,
            c,
            state,
            action,
            original,
            ChoiceAnswer.model_validate_json(json.dumps(body["selected"])),
        )
        return
    if kind == "harpy_beneath_pin_response":
        if (
            answer.denied
            or answer.fields
            or answer.flag is not None
            or answer.member is not None
            or answer.number is not None
        ):
            raise WorkflowError("The actual pinned person chooses only its own response")
        if answer.options == ("play",):
            game.request(
                c,
                action,
                actual(game, c, state, victim).controller,
                "harpy_beneath_response_play",
                json.loads(request["body_json"]),
            )
            return
        if answer.options not in ((), ("narrative",)) or not answer.text.strip():
            raise WorkflowError("Describe your own actual response or make a real response Play")
        action["data"]["result"]["pinned_response"] = answer.text
        finish(game, c, state, action)
        return
    if answer.flag is not None or answer.member is not None or answer.number is not None:
        raise WorkflowError("Use only this actual Beneath decision's fields")
    if kind == "harpy_beneath_select":
        if request["actor_id"] != str(actual(game, c, state, setter).controller) or answer.denied:
            raise WorkflowError("Only the real tier's chooser selects the printed effects")
        rules.choices(level, answer.options)
        legal = options(game, c, state, setter, victim, level)
        if set(answer.options) - set(
            legal["base"] + legal["extra"] + (["damage"] if level == "low" else [])
        ):
            raise WorkflowError(
                "Choose actual applicable effects; Harpy Status/authority is not invented"
            )
        if (
            not answer.text.strip()
            or set(answer.fields) - {"tag", "locked_tag", "issuer", "order"}
            or bool(answer.fields.get("tag", "").strip()) != ("tag" in answer.options)
            or bool(answer.fields.get("locked_tag")) != ("lock_tag" in answer.options)
        ):
            raise WorkflowError("Supply only the selected actual Tag and effect descriptions")
        if "punish" in answer.options:
            chosen_issuer = next(
                (
                    x
                    for x in order_issuers(game, c, state, victim)
                    if x["token"] == answer.fields.get("issuer")
                ),
                None,
            )
            if chosen_issuer is None or not answer.fields.get("order", "").strip():
                raise WorkflowError("Select the actual superior and state the exact real order")
            game.request(
                c,
                action,
                chosen_issuer["controller"],
                "harpy_beneath_order_confirmation",
                dict(
                    issuer=chosen_issuer["ref"],
                    instruction=answer.fields["order"],
                    selected=answer.model_dump(mode="json"),
                    source_choice=request["id"],
                ),
            )
            return
        if answer.fields.get("issuer") or answer.fields.get("order"):
            raise WorkflowError("An actual order applies only to selected Punishment")
        if "bond" in answer.options or "damage" in answer.options:
            game.request(
                c,
                action,
                actual(game, c, state, victim).controller,
                "harpy_beneath_details",
                dict(
                    options=list(answer.options),
                    source_choice=request["id"],
                    selected=answer.model_dump(mode="json"),
                ),
            )
        else:
            _apply_effects(game, c, state, action, request, answer)
        return
    if kind == "harpy_beneath_details":
        if (
            request["actor_id"] != str(actual(game, c, state, victim).controller)
            or answer.options
            or answer.text
        ):
            raise WorkflowError("The actual affected owner chooses its private resource detail")
        body = json.loads(request["body_json"])
        selected = ChoiceAnswer.model_validate_json(json.dumps(body["selected"]))
        if "bond" in selected.options:
            if set(answer.fields) != {"bond"} or answer.denied:
                raise WorkflowError("Choose one actual existing Bond")
            peer = next(
                (x for x in bonds(game, c, state, victim) if x["token"] == answer.fields["bond"]),
                None,
            )
            if peer is None:
                raise WorkflowError("Reopen the actual original affected Bond choices")
            _apply_effects(
                game, c, state, action, request, selected, peer=ActorRef.model_validate(peer["ref"])
            )
        else:
            if len(answer.denied) != 1 or answer.fields:
                raise WorkflowError("Choose one actual owned undamaged Asset")
            _apply_effects(game, c, state, action, request, selected, asset=answer.denied[0])
        return
    raise WorkflowError("Resume this actual source-owned Beneath response")


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_battle import synchronize_damage

    synchronize_damage(game, c, event)
    current = game.action(c, action["id"])
    if (
        current["data"][rules.MARKER].get("damage_followups")
        and not game.pending(c, current["id"])
        and current["state"] != "complete"
    ):
        finish(game, c, load_state(c, game.store.campaign_id), current)
        game.save_action(c, current)


def prove_permission(
    game: GameService, c: Connection, state: GameState, gate: Obligation
) -> tuple[ActorRef, ActorRef]:
    """Called by the existing permission service before using typed fresh Harpy roles."""
    locker, bearer = rules.participants(gate)
    action = game.action(c, gate.action)
    validate(game, c, state, action)
    first, second = rules.roles(action, action["data"]["result"]["tier"])
    if (locker, bearer) != (first, second) or (gate.owner, gate.target) != (
        actual(game, c, state, locker).controller,
        actual(game, c, state, bearer).controller,
    ):
        raise WorkflowError("Preserve the actual original locker and bearer of this Tag")
    responses = t.m2["m2_responses"]
    event = c.scalar(
        sa.select(responses.c.event_id).where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.choice_id == gate.details.get("effect_choice"),
        )
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    original = GameState.model_validate_json(raw) if raw else None
    if original is None or not any(
        x.get("kind") == rules.MARKER
        and x.get("action") == action["id"]
        and x.get("choice") == gate.details.get("source_choice")
        and x.get("event") == event
        and x.get("setter") == locker.model_dump_json()
        and x.get("victim") == bearer.model_dump_json()
        and "lock_tag" in json.loads(x["options"])
        for x in original.facts
    ):
        raise WorkflowError("Recover this exact original Tag lock effect and owned response")
    return locker, bearer


def validate_response_child(
    game: GameService, c: Connection, parent: dict[str, Any], ref: ActorRef, prepared: PlayInput
) -> dict[str, Any]:
    from girlframe.services.m2_state import load_state

    state = load_state(c, game.store.campaign_id)
    validate(game, c, state, parent)
    _, victim = rules.roles(parent, parent["data"]["result"]["tier"])
    row = next(
        (
            x
            for x in game.pending(c, parent["id"])
            if x["kind"] == "harpy_beneath_response_play"
            and x["actor_id"] == str(actual(game, c, state, victim).controller)
        ),
        None,
    )
    if row is None or victim != ref or prepared.parent != parent["id"] or prepared.source_work:
        raise WorkflowError("Only the actual pinned person makes this original response Play")
    return dict(parent=parent["id"], choice=row["id"], actor=ref.model_dump(mode="json"))


def complete_response_child(
    game: GameService, c: Connection, child: dict[str, Any], event: str
) -> None:
    source = child["data"].get("harpy_beneath_response_source")
    if source is None or child["state"] != "complete":
        return
    parent = game.action(c, source["parent"])
    _, victim = rules.roles(parent, parent["data"]["result"]["tier"])
    actual_child = child["data"].get("actor_basic", {}).get("ref")
    if (
        child.get("parent_id") != parent["id"]
        or source["actor"] != victim.model_dump(mode="json")
        or (actual_child is not None and actual_child != source["actor"])
    ):
        raise WorkflowError("Complete only the actual original pinned person's child response")
    table = t.m2["m2_choices"]
    c.execute(
        table.update()
        .where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == source["choice"],
            table.c.state == "pending",
        )
        .values(state="completed_by_work", revision=table.c.revision + 1)
    )
    from girlframe.services.m2_state import load_state

    finish(game, c, load_state(c, game.store.campaign_id), parent)
    game.save_action(c, parent)


def order_issuers(
    game: GameService, c: Connection, state: GameState, victim: ActorRef
) -> list[dict[str, Any]]:
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_handler_consequences import active_handler

    if victim.kind != "pilot":
        return []
    refs = [
        current_ref(state, uid)
        for uid in state.order
        if uid != int(victim.entity) and higher(state, uid, int(victim.entity))
    ]
    handler = active_handler(state)
    if handler is not None:
        refs.append(handler)
    return [
        dict(
            token=ref.token,
            ref=ref.model_dump(mode="json"),
            label=actual(game, c, state, ref).label,
            controller=actual(game, c, state, ref).controller,
        )
        for ref in refs
    ]


def prove_authority(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    authority: dict[str, Any] | None,
    pending: bool = False,
) -> None:
    setter, victim = rules.roles(action, action["data"]["result"]["tier"])
    if not isinstance(authority, dict) or victim.kind != "pilot" or setter.kind != "external_pilot":
        raise WorkflowError("Use a real superior's actual order to this Harpy against this Girl")
    issuer = ActorRef.model_validate(authority["issuer"])
    if (
        authority.get("recipient") != setter.model_dump(mode="json")
        or authority.get("target") != victim.model_dump(mode="json")
        or authority.get("source_action") != action["id"]
        or not authority.get("instruction", "").strip()
    ):
        raise WorkflowError("The actual issuing superior must outrank this original Girl")
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == authority["choice"],
                t.m2["m2_choices"].c.action_id == action["id"],
                t.m2["m2_choices"].c.kind == "harpy_beneath_order_confirmation",
                t.m2["m2_choices"].c.actor_id == str(actual(game, c, state, issuer).controller),
                t.m2["m2_choices"].c.state == "answered",
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the actual issuer-owned confirmed source order")
    if pending and authority["event"] == action["data"].get("response_event"):
        if issuer.token not in {x["token"] for x in order_issuers(game, c, state, victim)}:
            raise WorkflowError("The actual issuing superior must outrank the original Girl")
        return
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == authority["event"],
        )
    )
    original = GameState.model_validate_json(raw) if raw else None
    if (
        original is None
        or issuer.token not in {x["token"] for x in order_issuers(game, c, original, victim)}
        or not any(
            x.get("kind") == "harpy_beneath_order"
            and x.get("action") == action["id"]
            and json.loads(x["body"]) == authority
            for x in original.facts
        )
    ):
        raise WorkflowError("Recover this real superior's original source-bound order history")


def prove_punishment(
    game: GameService, c: Connection, state: GameState, case: RolePunishment
) -> dict[str, Any]:
    if case.action is None:
        raise WorkflowError("Recover the actual original Beneath source action")
    action = game.action(c, case.action)
    setter, victim = rules.roles(action, action["data"]["result"]["tier"])
    authority = action["data"][rules.MARKER].get("authority")
    prove_authority(game, c, state, action, authority)
    if (
        case.source_kind != "harpy_beneath"
        or case.executor != setter
        or case.chooser != setter
        or case.subject != victim
        or case.id != action["data"][rules.MARKER].get("punishment")
        or case.executor_controller != actual(game, c, state, setter).controller
        or case.chooser_controller != actual(game, c, state, setter).controller
        or case.subject_controller != actual(game, c, state, victim).controller
    ):
        raise WorkflowError(
            "Preserve the actual Harpy executor, original Girl and superior's order"
        )
    return action


def complete_punishment(game: GameService, c: Connection, case: RolePunishment, event: str) -> None:
    from girlframe.services.m2_state import load_state

    state = load_state(c, game.store.campaign_id)
    action = prove_punishment(game, c, state, case)
    if case.completion_event is None:
        return
    choices = t.m2["m2_choices"]
    for row in game.pending(c, action["id"]):
        if (
            row["kind"] == "harpy_beneath_punishment"
            and json.loads(row["body_json"]).get("case") == case.id
        ):
            c.execute(
                choices.update()
                .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == row["id"])
                .values(state="completed_by_work", revision=choices.c.revision + 1)
            )
    if not game.pending(c, action["id"]):
        finish(game, c, state, action)
        game.save_action(c, action)
