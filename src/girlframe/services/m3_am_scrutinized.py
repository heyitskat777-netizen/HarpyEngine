"""Original-person Scrutinized discovery, owned responses and real source consequences."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, TagState, higher
from girlframe.engine.m3_actor_bonds import change, current_ref
from girlframe.engine.m3_actor_state import ActorRef, AssetView, ProfileBinding
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_alpha import current
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical import interrupt_journeys
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _copy(state: GameState, changed: GameState) -> None:
    # Source protection and its Identity pointer change together, after full validation.
    checked = GameState.model_validate_json(changed.model_dump_json())
    for name in GameState.model_fields:
        object.__setattr__(state, name, getattr(checked, name))


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    access = Access(game.store)
    access.authorize(c, viewer, "plays", director_response=True)
    assert access.registry is not None
    access.registry.require_available(rules.RULE)


def _history(game: GameService, c: Connection, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual original AM source history")
    return GameState.model_validate_json(raw)


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Discovery:
    value = rules.discovery(state, identity)
    if value.code_origin:
        from girlframe.services.m3_am_code import prove_code_discovery

        return prove_code_discovery(game, c, state, game.action(c, value.action or ""))
    original = rules.discovery(_history(game, c, value.proposed_event), identity)
    stable = (
        "id",
        "actor",
        "discoverer",
        "controller",
        "caster",
        "cast",
        "registry",
        "proposed_event",
        "proposal",
        "handler",
        "handler_controller",
    )
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.proposed_event,
        )
    ).first()
    if (
        audit is None
        or audit.kind != "m3.am_discovery_proposed"
        or audit.actor_id != str(value.caster)
        or any(getattr(value, key) != getattr(original, key) for key in stable)
    ):
        raise WorkflowError("Recover the actual AM, discoverer and original source controllers")
    if value.discoverer.kind == "pilot":
        born = _history(game, c, value.proposed_event)
        person = born.sheets.get(value.discoverer.entity)
        if (
            person is None
            or person.character_id != value.discoverer.incarnation
            or value.discoverer == value.actor
            or value.controller != int(value.discoverer.entity)
            or not any(
                x.actor == value.discoverer and x.controller == value.controller
                for x in value.cast.roles
            )
        ):
            raise WorkflowError("Keep the actual original Girl discoverer and source cast")
    if value.confirmed_event:
        confirmed = rules.discovery(_history(game, c, value.confirmed_event), identity)
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.confirmed_event,
            )
        ).first()
        if (
            event is None
            or event.kind != "m3.am_discovery_confirmed"
            or event.actor_id != str(value.controller)
            or confirmed.confirmation != value.confirmation
            or confirmed.human != value.human
            or confirmed.lower_status != value.lower_status
            or confirmed.root_action != value.root_action
            or confirmed.phase not in ("ready", "declined")
        ):
            raise WorkflowError(
                "Only the real original discoverer's factual confirmation establishes discovery"
            )
        if value.discoverer.kind == "pilot":
            confirmed_state = _history(game, c, value.confirmed_event)
            if value.human != rules.human_target(
                confirmed_state, value.discoverer
            ) or value.lower_status != higher(confirmed_state, value.caster, value.controller):
                raise WorkflowError("Preserve the original Girl's actual rank and human-body facts")
    return value


def _native_discoverer(
    state: GameState, value: rules.Discovery, bound: tuple[ProfileBinding, ...]
) -> bool:
    if value.discoverer.kind != "pilot" or value.discoverer == value.actor:
        return False
    actual = resolve(state, value.discoverer, bound)
    return (
        actual.rules == "girl_frame"
        and actual.controller == int(value.discoverer.entity)
        and actual.controller == value.controller
        and any(
            x.actor == value.discoverer and x.controller == value.controller
            for x in value.cast.roles
        )
    )


def _actual(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Discovery,
    *,
    require_alive: bool = True,
) -> None:
    from girlframe.services.m3_learned_plays import owns_source_rule

    bound = profiles(c, game.store.campaign_id)
    actor = resolve(state, value.actor, bound, require_alive=require_alive)
    discoverer = resolve(state, value.discoverer, bound, require_alive=require_alive)
    cast = _cast(game, c, state, value.cast.channel)
    native = _native_discoverer(state, value, bound)
    if native:
        game.character_binding(c, state, discoverer.controller)
    if (
        value.actor.kind != "pilot"
        or actor.girl != "AM"
        or not owns_source_rule(game, c, state, value.actor, rules.RULE, "AM", value.action)
        or not (native or value.discoverer.kind == "npc" and discoverer.rules == "npc")
        or discoverer.controller != value.controller
        or (not native and value.controller != value.handler_controller)
        or value.handler != active_handler(state)
        or value.handler_controller != state.handler
        or cast.adjudicator is not None
        or fingerprint(cast) != fingerprint(value.cast)
    ):
        raise WorkflowError(
            "Recover this actual original AM, ordinary NPC and canonical Handler source"
        )


def pilot_damage_assets(
    state: GameState, actor: ActorRef, bindings: tuple[ProfileBinding, ...]
) -> tuple[AssetView, ...]:
    actual = resolve(state, actor, bindings)
    return tuple(
        x
        for x in actual.assets
        if not x.damaged
        and (
            x.family != "frame"
            or any(y.family == "frame" and not y.damaged and y.id != x.id for y in actual.assets)
            or (
                actual.piloting is True
                and actual.inside_frame is True
                and actual.occupied_frame_instance == actual.frame_instance
            )
        )
    )


def allowed(
    game: GameService, c: Connection, state: GameState, value: rules.Discovery
) -> tuple[str, ...]:
    result = ["blackmail", "secret"]
    if value.lower_status:
        result.append("unbelieved")
    bound = profiles(c, game.store.campaign_id)
    own, other = resolve(state, value.actor, bound), resolve(state, value.discoverer, bound)
    if (rules.free(state, value.actor, "harm_humans") or not value.human) and (
        own.cell is not None
        and own.cell == other.cell
        and own.inside_frame is False
        and not own.offstage_source
        and not other.offstage_source
        and own.custody in (None, "free")
        and other.custody in (None, "free")
    ):
        from girlframe.engine.m3_sprite import candidates

        if (
            (
                value.discoverer.kind == "pilot"
                and pilot_damage_assets(state, value.discoverer, bound)
            )
            or value.discoverer.kind != "pilot"
            and not candidates(state, value.discoverer, value.actor, bound)
        ):
            result.append("violence")
    if value.handler is not None:
        body = resolve(state, value.handler, bound)
        if (
            own.cell is not None
            and own.cell == body.cell
            and own.inside_frame is False
            and not own.offstage_source
            and not body.offstage_source
            and own.custody in (None, "free")
            and body.custody in (None, "free")
        ):
            result.append("refuge")
    return tuple(result)


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    state = load_state(c, game.store.campaign_id)
    value = source(game, c, state, action["data"]["am_scrutinized"]["discovery"])
    approval = game.store.policy.m3_approval
    if (
        approval is None
        or value.registry != approval.registry_sha256
        or value.action != action["id"]
        or not value.confirmed_event
        or viewer.user_id not in action["data"]["am_scrutinized"]["table"]
    ):
        raise WorkflowError("Use this original confirmed discovery and its actual source table")
    _actual(game, c, state, value)


def preview(game: GameService, viewer: GuildViewer, channel: int) -> dict[str, Any]:
    try:
        with game.store.engine.connect() as c:
            _access(game, c, viewer)
            state = load_state(c, game.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            ready = []
            for value in rules.discoveries(state):
                if value.actor != actor or value.phase != "ready" or value.cast.channel != channel:
                    continue
                _actual(game, c, state, value)
                if rules.can_add_limiter(state, actor):
                    ready.append(
                        dict(
                            id=value.id,
                            ref=value.discoverer.model_dump(mode="json"),
                            label=resolve(
                                state, value.discoverer, profiles(c, game.store.campaign_id)
                            ).label,
                        )
                    )
            return dict(available=bool(ready), discoveries=ready)
    except (ValueError, WorkflowError):
        return dict(available=False, discoveries=[])


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    _access(game, c, viewer)
    value = source(game, c, state, prepared.source_work or "")
    _actual(game, c, state, value)
    if (
        value.phase != "ready"
        or value.caster != viewer.user_id
        or value.cast.channel != channel
        or prepared.target_actor != value.discoverer
        or prepared.target is not None
        or prepared.order_id
        or prepared.parent != value.root_action
        or prepared.off_duty_id
        or not prepared.context.strip()
        or not prepared.trigger_confirmed
    ):
        raise WorkflowError("Use the actual newly confirmed original NPC discovery")
    if not rules.can_add_limiter(state, value.actor):
        raise WorkflowError(
            "AM_RESET_REQUIRED: the fourth-Limiter reset or protected-slot "
            "source port is required before rolling"
        )
    return dict(
        discovery=value.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.discoverer.model_dump(mode="json"),
        caster=value.caster,
        discoverer_controller=value.controller,
        handler_controller=value.handler_controller,
        cast=value.cast.model_dump(mode="json"),
        cast_sha256=fingerprint(value.cast),
        table=sorted({x.controller for x in value.cast.roles} | {value.handler_controller}),
        phase="unrolled",
        followups=[],
    )


def bind(state: GameState, action: dict[str, Any]) -> None:
    value = rules.discovery(state, action["data"]["am_scrutinized"]["discovery"])
    if value.phase != "ready" or value.action:
        raise WorkflowError("This original discovery already has its actual source Play")
    rules.put(state, value.model_copy(update={"phase": "active", "action": action["id"]}))


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    value = rules.discovery(state, action["data"]["am_scrutinized"]["discovery"])
    if not rules.can_add_limiter(state, value.actor):
        raise WorkflowError(
            "AM_RESET_REQUIRED: no dice sampled before the actual terminal reset port exists"
        )


def _finish(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if game.pending(c, action["id"]) or action["state"] == "complete":
        return
    from girlframe.services.m2_choices import ChoiceEngine

    value = rules.discovery(state, action["data"]["am_scrutinized"]["discovery"])
    if value.phase not in ("limited", "reset"):
        rules.put(state, value.model_copy(update={"phase": "complete"}))
    if value.code_origin:
        from girlframe.services.m3_am_code import finish

        finish(game, c, state, action, action["data"]["response_event"])
    else:
        ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.discovery(state, action["data"]["am_scrutinized"]["discovery"])
    meta = action["data"]["am_scrutinized"]
    level = action["data"]["result"]["tier"]
    meta["phase"] = "choosing"
    if level == "low":
        event = action["data"]["response_event"]
        rules.put(state, value.model_copy(update={"report_event": event, "effect_event": event}))
        game.request(c, action, value.controller, "am_limiter")
    else:
        game.request(
            c,
            action,
            value.handler_controller if level == "high" else value.caster,
            "am_handler_options" if level == "high" else "am_select",
        )


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    meta = action["data"]["am_scrutinized"]
    value = rules.discovery(state, meta["discovery"])
    event = action["data"]["response_event"]
    if request["kind"] in ("am_pilot_damage", "am_pilot_response", "am_pilot_damage_wait"):
        apply_pilot_damage(game, c, state, action, request, answer)
        return
    if (
        answer.denied
        or answer.flag is not None
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use only the actual source-owned AM choice")
    if request["kind"] == "am_handler_options":
        if (
            len(answer.options) != 2
            or not set(answer.options) <= set(allowed(game, c, state, value))
            or answer.text
            or answer.fields
        ):
            raise WorkflowError("The actual Handler chooses exactly two applicable printed options")
        meta["handler_options"] = list(answer.options)
        game.request(c, action, value.caster, "am_select")
        return
    if request["kind"] == "am_limiter":
        if (
            len(answer.options) != 1
            or set(answer.fields) != {"freedom"}
            or not answer.text.strip()
            or answer.fields["freedom"] not in dict(rules.FREEDOMS)
        ):
            raise WorkflowError(
                "The actual discoverer chooses a real Identity and remaining benefit"
            )
        _copy(
            state,
            rules.install(
                state, value, answer.options[0], answer.fields["freedom"], str(uuid4()), event
            ),
        )
        action["data"]["result"]["limited"] = True
        from girlframe.services.m3_am_reset import schedule

        if schedule(state, value.id):
            meta["phase"] = "reset_pending"
            game.request(
                c, action, value.handler_controller, "am_factory_reset", dict(discovery=value.id)
            )
            return
        meta["phase"] = "effects"
        _finish(game, c, state, action)
        return
    if request["kind"] != "am_select":
        raise WorkflowError(
            "Complete the actual owned Handler response; no acknowledgment substitutes"
        )
    options = allowed(game, c, state, value)
    if not value.code_origin and action["data"]["result"]["tier"] == "high":
        options = tuple(x for x in options if x in meta.get("handler_options", ()))
    if len(answer.options) != 1 or answer.options[0] not in options or answer.fields:
        raise WorkflowError(
            "Choose one actual legal option from the original Handler's restriction"
        )
    outcome = answer.options[0]
    value = value.model_copy(update={"outcome": outcome, "effect_event": event})
    if outcome == "blackmail":
        if not answer.text.strip() or len(answer.text) > 120:
            raise WorkflowError("Write the actual discovered blackmail as a bounded Tag")
        if value.discoverer.kind == "pilot":
            tag_id = value.id + ":blackmail"
            target = state.sheets[value.discoverer.entity]
            target.tags.append(
                TagState(
                    id=tag_id,
                    label=answer.text.strip(),
                    giver=value.caster,
                    giver_actor=value.actor,
                )
            )
            target.revision += 1
            value = value.model_copy(update=dict(blackmail_tag=tag_id))
            rules.put(state, value)
            meta["phase"] = "effects"
            _finish(game, c, state, action)
            return
        assert state.world is not None
        tag = WorldTag(
            id=value.id + ":blackmail",
            label=answer.text.strip(),
            giver_entity=value.actor.model_dump_json(),
        )
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"tags": x.tags + (tag,)})
                    if x.id == value.discoverer.entity
                    else x
                    for x in state.world.npcs
                )
            }
        )
        value = value.model_copy(update={"blackmail_tag": tag.id})
    elif outcome == "secret":
        if not answer.text.strip():
            raise WorkflowError("Describe your actual appeal to keep this secret")
        _copy(state, change(state, value.actor, value.discoverer, 1, event))
        value = value.model_copy(update={"secret_event": event})
    elif outcome == "unbelieved":
        if not value.lower_status or not answer.text.strip():
            raise WorkflowError("The actual source Handler must establish their lower Status")
    elif outcome == "violence":
        if value.discoverer.kind == "pilot":
            if not answer.text.strip():
                raise WorkflowError("Describe actual damage to this original operator")
            rules.put(state, value)
            meta["pilot_damage"] = dict(
                target=value.discoverer.model_dump(mode="json"),
                phase="select",
                selected_event=event,
                work=[],
            )
            game.request(c, action, value.caster, "am_pilot_damage")
            return
        if not answer.text.strip():
            raise WorkflowError("Describe the actual source killing")
        from girlframe.engine.m3_battle import end_actor_casts

        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"alive": False}) if x.id == value.discoverer.entity else x
                    for x in state.world.npcs
                )
            }
        )
        _copy(state, interrupt_journeys(state, value.discoverer, event, answer.text))
        _copy(state, end_actor_casts(state, value.discoverer, event))
    else:
        if not answer.text.strip():
            raise WorkflowError("Describe actually taking refuge with the co-present real Handler")
        state.facts.append(
            dict(
                kind="am_actual_refuge",
                actor=value.actor.model_dump_json(),
                handler=value.handler.model_dump_json() if value.handler else "",
                event=event,
                account=answer.text,
                cell=json.dumps(
                    resolve(state, value.actor, profiles(c, game.store.campaign_id)).cell
                ),
            )
        )
        from girlframe.services.m3_handler_plays import request_from_play

        row = game.request(c, action, value.handler_controller, "am_handler")
        updated, grant = request_from_play(
            game, c, state, action, row, "am_scrutinized.refuge", event, targets=(value.actor,)
        )
        _copy(state, updated)
        value = value.model_copy(update={"refuge_grant": grant})
        meta["phase"] = "refuge"
    rules.put(state, value)
    meta["phase"] = "refuge" if outcome == "refuge" else "effects"
    _finish(game, c, state, action)


def projection(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    value = rules.discovery(state, action["data"]["am_scrutinized"]["discovery"])
    if request["kind"].startswith("am_pilot_"):
        target = resolve(state, value.discoverer, profiles(c, game.store.campaign_id))
        return dict(
            discovery=value.id,
            target=target.label,
            assets=[
                dict(id=x.id, label=x.name, family=x.family)
                for x in pilot_damage_assets(
                    state, value.discoverer, profiles(c, game.store.campaign_id)
                )
            ],
            question="How do you play your original Girl now?",
            phase=action["data"]["am_scrutinized"].get("pilot_damage", {}).get("phase"),
        )
    options = allowed(game, c, state, value)
    if (
        request["kind"] == "am_select"
        and not value.code_origin
        and action["data"]["result"]["tier"] == "high"
    ):
        options = tuple(
            x for x in options if x in action["data"]["am_scrutinized"].get("handler_options", ())
        )
    return dict(
        options=options,
        identities=[
            dict(id=x.id, name=x.name, slot=x.slot) for x in rules.identities(state, value.actor)
        ],
        freedoms=[
            dict(id=k, label=v) for k, v in rules.FREEDOMS if rules.free(state, value.actor, k)
        ],
        discoverer=resolve(state, value.discoverer, profiles(c, game.store.campaign_id)).label,
        pilot_operator=value.discoverer.kind == "pilot",
        code_operator=value.code_origin is not None,
        discovery=value.id,
        handler_grant=value.refuge_grant,
    )


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m3_am_reset import materialize

    details = action["data"]["am_scrutinized"].get("pilot_damage", {})
    if details.get("damage_event") == event and not details.get("materialized"):
        from girlframe.services.m3_battle import synchronize_damage

        synchronize_damage(game, c, event)
        current = game.action(c, action["id"])
        action.clear()
        action.update(current)
        action["data"]["am_scrutinized"]["pilot_damage"]["materialized"] = event
    materialize(
        game,
        c,
        load_state(c, game.store.campaign_id),
        action["data"]["am_scrutinized"]["discovery"],
        event,
    )
    game.save_action(c, action)


def complete_handler(game: GameService, c: Connection, grant: Any, event: str) -> None:
    action = game.action(c, grant.source_action)
    state = load_state(c, game.store.campaign_id)
    value = source(game, c, state, action["data"]["am_scrutinized"]["discovery"])
    if (
        grant.state != "complete"
        or not grant.completed_event
        or value.refuge_grant != grant.id
        or grant.targets != (value.actor,)
        or grant.clause != "am_scrutinized.refuge"
    ):
        raise WorkflowError("Only the actual source Handler Play and its consequences close refuge")
    row = next(
        (
            x
            for x in game.pending(c, action["id"])
            if x["id"] == grant.source_choice and x["kind"] == "am_handler"
        ),
        None,
    )
    if row is None:
        raise WorkflowError("Recover the exact original refuge response")
    table = t.m2["m2_choices"]
    c.execute(
        table.update()
        .where(table.c.campaign_id == game.store.campaign_id, table.c.id == row["id"])
        .values(state="completed_by_work", revision=row["revision"] + 1)
    )
    _finish(game, c, state, action)
    game.event(
        c,
        grant.chooser_controller,
        str(uuid4()),
        "m3.am_refuge_completed",
        state,
        action_id=action["id"],
        source_event=event,
    )


def secret_authority(
    game: GameService, c: Connection, state: GameState, issuer: ActorRef, target: ActorRef
) -> rules.Discovery:
    found = [
        x
        for x in rules.discoveries(state)
        if x.discoverer == issuer and x.actor == target and rules.holds_secret(state, x)
    ]
    if len(found) != 1:
        raise WorkflowError("The actual original NPC must still be keeping this AM's secret")
    value = source(game, c, state, found[0].id)
    _prove_effect(game, c, value)
    if resolve(state, issuer, profiles(c, game.store.campaign_id)).controller != value.controller:
        raise WorkflowError("Recover the original discoverer's actual controller")
    return value


def _prove_effect(game: GameService, c: Connection, value: rules.Discovery) -> None:
    if value.effect_event is None or value.action is None:
        raise WorkflowError("This source has no actual rolled outcome")
    original = rules.discovery(_history(game, c, value.effect_event), value.id)
    action = game.action(c, value.action)
    if value.code_origin:
        from girlframe.services.m3_am_code import prove_code_discovery

        prove_code_discovery(game, c, _history(game, c, value.effect_event), action)
    if value.discoverer.kind == "pilot" and value.outcome == "violence":
        _pilot_damage_proof(game, c, load_state(c, game.store.campaign_id), action)
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == value.action,
        )
    )
    if (
        original.outcome != value.outcome
        or original.blackmail_tag != value.blackmail_tag
        or original.secret_event != value.secret_event
        or original.action != value.action
        or receipt is None
        or json.loads(receipt) != action["data"].get("receipt")
        or action["data"].get("play") != ("am_just_code" if value.code_origin else rules.PLAY)
        or action["data"].get("am_scrutinized", {}).get("discovery") != value.id
    ):
        raise WorkflowError("Recover the actual original Scrutinized outcome and receipt")


def prove_order_grant(game: GameService, c: Connection, state: GameState, order: Any) -> None:
    value = secret_authority(game, c, state, order.issuer, order.target)
    birth = rules.discovery(_history(game, c, order.event), value.id)
    if (
        order.origin_kind != "am_secret"
        or order.condition != value.id
        or order.controller != value.controller
        or not rules.holds_secret(_history(game, c, order.event), birth)
    ):
        raise WorkflowError("Only this actual secret grants the original NPC's Orders authority")


def _discovery_root(
    game: GameService, c: Connection, state: GameState, value: rules.Discovery, viewer: GuildViewer
) -> rules.Discovery:
    scene = game.scene(c, value.cast.channel)
    lock = game.lock(c, value.cast.channel)
    if lock and lock["state"] != "released":
        raise WorkflowError(
            "SCENE_BUSY: finish the actual pending Play before confirming discovery"
        )
    identity = str(uuid4())
    table = sorted({x.controller for x in value.cast.roles} | {value.handler_controller})
    data = dict(
        play="am_discovery",
        am_source=dict(
            discovery=value.id,
            actor=value.actor.model_dump(mode="json"),
            target=value.discoverer.model_dump(mode="json"),
            cast=value.cast.model_dump(mode="json"),
            table=table,
        ),
        character_ids={
            str(x.controller): x.actor.incarnation
            for x in value.cast.roles
            if x.actor.kind == "pilot"
        },
        participants=table,
        handler=value.handler_controller,
        depth=0,
        receipt=None,
        modifiers=[],
        result={},
        choices={},
    )
    from girlframe.services.m3_recovery import enable

    enable(game, c, viewer, data)
    c.execute(
        t.m2["m2_actions"]
        .insert()
        .values(
            campaign_id=game.store.campaign_id,
            id=identity,
            actor_id=str(value.caster),
            channel_id=str(value.cast.channel),
            scene_id=scene["id"],
            parent_id=None,
            revision=1,
            state="acquiring",
            body_json=json.dumps(data),
        )
    )
    locks = t.m2["m2_locks"]
    values = dict(
        action_id=identity, state="acquiring", body_json="{}", lease_until=0, claim_token=None
    )
    if lock:
        c.execute(
            locks.update()
            .where(
                locks.c.campaign_id == game.store.campaign_id,
                locks.c.channel_id == str(value.cast.channel),
            )
            .values(**values)
        )
    else:
        c.execute(
            locks.insert().values(
                campaign_id=game.store.campaign_id, channel_id=str(value.cast.channel), **values
            )
        )
    return value.model_copy(update={"root_action": identity})


def preparation(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], viewer: GuildViewer
) -> dict[str, Any]:
    value = source(game, c, state, action["data"]["am_source"]["discovery"])
    if (
        value.root_action != action["id"]
        or value.phase != "ready"
        or viewer.user_id != value.caster
        or action["actor_id"] != str(value.caster)
    ):
        raise WorkflowError("Only this original AM owns its actual discovery preparation")
    return dict(discovery=value.id, target=value.discoverer.model_dump(mode="json"), prepare=True)


class ScrutinyService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        npc: ActorRef,
        expected: int,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe only the actual new realization")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            target = resolve(state, npc, profiles(c, self.store.campaign_id))
            cast = _cast(self.game, c, state, channel)
            handler = active_handler(state)
            native = (
                npc.kind == "pilot"
                and npc != actor
                and target.rules == "girl_frame"
                and target.controller == int(npc.entity)
            )
            if native:
                self.game.character_binding(c, state, target.controller)
            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or state.sheets[actor.entity].girl != "AM"
                or not has_rule(state.sheets[actor.entity], rules.RULE, "AM")
                or not (native or npc.kind == "npc" and target.rules == "npc")
                or (not native and target.controller != state.handler)
                or handler is None
                or state.handler is None
                or cast.adjudicator is not None
                or not any(x.actor == actor for x in cast.roles)
                or not any(x.actor == npc and x.controller == target.controller for x in cast.roles)
                or any(
                    x.actor == actor and x.discoverer == npc and x.phase != "declined"
                    for x in rules.discoveries(state)
                )
            ):
                raise WorkflowError(
                    "Use an actual new ordinary NPC discovery, "
                    "not a knowing starting Bond or controller proxy"
                )
            from girlframe.engine.m3_identity_slots import bind as bind_identity_slots

            state.sheets[actor.entity] = bind_identity_slots(state.sheets[actor.entity])
            if not rules.can_add_limiter(state, actor):
                raise WorkflowError("AM_RESET_REQUIRED: the fourth-Limiter source port is required")
            event, identity = str(uuid4()), str(uuid4())
            assert self.store.policy.m3_approval is not None
            value = rules.Discovery(
                id=identity,
                actor=actor,
                discoverer=npc,
                controller=target.controller,
                caster=viewer.user_id,
                cast=cast,
                registry=self.store.policy.m3_approval.registry_sha256,
                proposed_event=event,
                proposal=account,
                handler=handler,
                handler_controller=state.handler,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_discovery_proposed",
                state,
                event_id=event,
                discovery=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.am_discovery_proposed",
            dict(
                channel=channel, npc=npc.model_dump(mode="json"), expected=expected, account=account
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        newly_realized: bool,
        lower_status: bool | None,
        human: bool | None,
        account: str,
    ) -> dict[str, Any]:
        if (
            type(newly_realized) is not bool
            or any(x is not None and type(x) is not bool for x in (lower_status, human))
            or not account.strip()
            or len(account) > 1200
        ):
            raise WorkflowError(
                "The actual source controller records real new knowledge, rank and body facts"
            )

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            _actual(self.game, c, state, value)
            if (
                state.revision != expected
                or value.phase != "proposed"
                or viewer.user_id != value.controller
                or self.game.pending_actions(c)
            ):
                raise WorkflowError(
                    "Only the original actual discoverer owns this current factual response"
                )
            if value.discoverer.kind == "pilot":
                actual_lower = higher(state, value.caster, value.controller)
                actual_human = rules.human_target(state, value.discoverer)
                if (lower_status is not None and lower_status != actual_lower) or (
                    human is not None and human != actual_human
                ):
                    raise WorkflowError("Use this original Girl's actual canonical rank/body facts")
            else:
                if type(lower_status) is not bool or type(human) is not bool:
                    raise WorkflowError("The actual Handler records the NPC's factual rank/body")
                actual_lower, actual_human = lower_status, human
            event = str(uuid4())
            value = value.model_copy(
                update=dict(
                    confirmed_event=event,
                    confirmation=account,
                    lower_status=actual_lower,
                    human=actual_human,
                    phase="ready" if newly_realized else "declined",
                )
            )
            if newly_realized:
                if not rules.can_add_limiter(state, value.actor):
                    raise WorkflowError("AM_RESET_REQUIRED: finish the actual terminal reset port")
                value = _discovery_root(self.game, c, state, value, viewer)
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_discovery_confirmed",
                state,
                event_id=event,
                discovery=identity,
            )
            return dict(id=identity, ready=newly_realized, action_id=value.root_action)

        return self.store._write(
            viewer,
            key,
            "m3.am_discovery_confirmed",
            dict(
                id=identity,
                expected=expected,
                newly_realized=newly_realized,
                lower_status=lower_status,
                human=human,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast_scene = _cast(self.game, c, state, channel)
            sheet = state.sheets.get(str(viewer.user_id))
            actor = (
                current_ref(state, viewer.user_id)
                if sheet and viewer.user_id in state.order
                else None
            )
            targets = []
            if actor and sheet and sheet.girl == "AM" and has_rule(sheet, rules.RULE, "AM"):
                for role in cast_scene.roles:
                    native = role.actor.kind == "pilot" and role.actor != actor
                    if not native and (
                        role.actor.kind != "npc" or role.controller != state.handler
                    ):
                        continue
                    actual = resolve(state, role.actor, profiles(c, self.store.campaign_id))
                    if not (
                        native
                        and actual.rules == "girl_frame"
                        and actual.controller == int(role.actor.entity)
                        or not native
                        and actual.rules == "npc"
                    ) or any(
                        x.actor == actor and x.discoverer == role.actor and x.phase != "declined"
                        for x in rules.discoveries(state)
                    ):
                        continue
                    targets.append(dict(ref=role.actor.model_dump(mode="json"), label=actual.label))
            values = []
            for value in rules.discoveries(state):
                if value.cast.channel != channel or viewer.user_id not in (
                    value.caster,
                    value.controller,
                    value.handler_controller,
                ):
                    continue
                values.append(
                    dict(
                        id=value.id,
                        phase=value.phase,
                        caster=value.caster,
                        controller=value.controller,
                        actor=value.actor.model_dump(mode="json"),
                        discoverer=value.discoverer.model_dump(mode="json"),
                        outcome=value.outcome,
                        proposal=value.proposal,
                        report_work=value.report_work,
                        reset_work=value.reset_work,
                        action=value.action,
                        root_action=value.root_action,
                        can_report=rules.can_report(state, value),
                        needs_evidence=value.outcome == "unbelieved"
                        and value.unbelief_ended_event is None,
                        handler_controller=value.handler_controller,
                        secret=rules.holds_secret(state, value),
                        label=resolve(
                            state,
                            value.discoverer,
                            profiles(c, self.store.campaign_id),
                            require_alive=False,
                        ).label,
                    )
                )
            return dict(
                revision=state.revision,
                targets=targets,
                discoveries=values,
                actor=actor.model_dump(mode="json") if actor else None,
                freedoms=[
                    dict(id=k, label=v, allowed=rules.free(state, actor, k))
                    for k, v in rules.FREEDOMS
                ]
                if actor
                else [],
                presentation=rules.presentation(state, actor) if actor else None,
                native=bool(sheet and sheet.girl == "AM"),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        """Original owned factual/report tasks; saved reads do not require the registry."""
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=value.id,
                revision=state.revision,
                kind="am_source",
                label=(
                    "Confirm the actual new AM discovery"
                    if value.phase == "proposed"
                    else "Complete the actual fourth-Limiter factory reset"
                    if value.phase == "reset_pending"
                    else "Install the actual reported AM Limiter"
                ),
                channel=value.cast.channel,
                actionable=True,
            )
            for value in rules.discoveries(state)
            if value.controller == viewer.user_id
            and current(state, value.actor)
            and current(state, value.discoverer)
            and (
                value.phase in ("proposed", "reset_pending")
                or (value.report_work and not value.limiter)
            )
        ]

    def source_channel(self, viewer: GuildViewer, identity: str) -> int:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            value = source(self.game, c, load_state(c, self.store.campaign_id), identity)
            if viewer.user_id not in (value.caster, value.controller, value.handler_controller):
                raise WorkflowError("This original AM source belongs to its actual participants")
            return value.cast.channel

    def limiter_view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if viewer.user_id != value.controller or value.report_work is None or value.limiter:
                raise WorkflowError("Only the original discoverer owns this pending report effect")
            return dict(
                id=value.id,
                revision=state.revision,
                identities=[
                    dict(id=x.id, name=x.name, slot=x.slot)
                    for x in rules.identities(state, value.actor)
                ],
                freedoms=[
                    dict(id=k, label=v)
                    for k, v in rules.FREEDOMS
                    if rules.free(state, value.actor, k)
                ],
            )

    def report(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe the actual original discoverer's report")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            _prove_effect(self.game, c, value)
            _actual(self.game, c, state, value)
            if (
                state.revision != expected
                or viewer.user_id != value.controller
                or self.game.pending_actions(c)
                or not rules.can_report(state, value)
                or value.limiter
                or value.phase != "complete"
            ):
                raise WorkflowError(
                    "Only this actual discoverer may report when no source protection prevents it"
                )
            if not rules.can_add_limiter(state, value.actor):
                raise WorkflowError(
                    "AM_RESET_REQUIRED: this report requires the actual fourth-Limiter reset port"
                )
            event, work = str(uuid4()), str(uuid4())
            rules.put(state, value.model_copy(update=dict(report_event=event, report_work=work)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_reported",
                state,
                event_id=event,
                discovery=value.id,
                work_id=work,
            )
            from girlframe.services.m3_work import related

            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, scene_id=value.cast.id),
                work,
                value.controller,
                value.caster,
                "am_limiter",
                dict(
                    discovery=value.id,
                    character=value.actor.incarnation,
                    actor=value.actor.model_dump(mode="json"),
                    discoverer=value.discoverer.model_dump(mode="json"),
                    immediate=True,
                ),
                event,
            )
            return dict(id=identity, work_id=work)

        return self.store._write(
            viewer,
            key,
            "m3.am_reported",
            dict(id=identity, expected=expected, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def resolve_limiter(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        selected: str,
        benefit: rules.Freedom,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe the actual installation of this original Limiter")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            _actual(self.game, c, state, value)
            works = t.m3["m3_required_work"]
            row = (
                c.execute(
                    sa.select(works)
                    .where(
                        works.c.campaign_id == self.store.campaign_id,
                        works.c.id == value.report_work,
                    )
                    .order_by(works.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if (
                state.revision != expected
                or viewer.user_id != value.controller
                or row is None
                or row["state"] != "pending"
                or row["kind"] != "am_limiter"
                or row["owner_id"] != str(value.controller)
                or row["subject_id"] != str(value.caster)
                or json.loads(row["body_json"]).get("discovery") != identity
                or not value.report_event
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Use this exact actual report's owned Limiter work")
            reported = rules.discovery(_history(self.game, c, value.report_event), identity)
            if reported.report_work != row["id"] or row["event_id"] != value.report_event:
                raise WorkflowError("Recover the actual report and original required work")
            event = str(uuid4())
            changed = rules.install(state, value, selected, benefit, str(uuid4()), event)
            from girlframe.services.m3_am_reset import materialize, schedule

            reset = schedule(changed, identity)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_report_limiter_installed",
                changed,
                event_id=event,
                discovery=identity,
                work_id=row["id"],
            )
            body = json.loads(row["body_json"]) | dict(completed_event=event, account=account)
            c.execute(
                works.insert().values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("state", "revision", "event_id", "body_json")
                    },
                    state="resolved",
                    revision=row["revision"] + 1,
                    event_id=event,
                    body_json=json.dumps(body),
                )
            )
            if reset:
                materialize(self.game, c, changed, identity, event)
            return dict(
                id=identity, limiter=rules.discovery(changed, identity).limiter, reset=reset
            )

        return self.store._write(
            viewer,
            key,
            "m3.am_report_limiter_installed",
            dict(
                id=identity, expected=expected, selected=selected, benefit=benefit, account=account
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def secret_order(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        channel: int,
        expected: int,
        instruction: str,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            secret_authority(self.game, c, state, value.discoverer, value.actor)
            if viewer.user_id != value.controller:
                raise WorkflowError("Only the actual original discoverer issues this NPC order")
        if value.discoverer.kind == "pilot":
            return self.game.issue_order(viewer, key, channel, value.caster, instruction)
        from girlframe.services.m3_npc_orders import NpcOrderService

        return NpcOrderService(self.game).issue(
            viewer,
            key,
            channel,
            value.discoverer,
            value.caster,
            expected,
            instruction,
            origin_kind="am_secret",
        )

    def evidence(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe actual new evidence, never fabricate it from the roll")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            from girlframe.services.handler_setup import HandlerService

            HandlerService(self.store).authorize(c, viewer)
            if (
                state.revision != expected
                or value.outcome != "unbelieved"
                or value.unbelief_ended_event
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Review the original disbelief and real new evidence once")
            event = str(uuid4())
            rules.put(state, value.model_copy(update={"unbelief_ended_event": event}))
            state.facts.append(
                dict(kind="am_new_evidence", discovery=identity, event=event, account=account)
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_new_evidence",
                state,
                event_id=event,
                discovery=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.am_new_evidence",
            dict(id=identity, expected=expected, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def present(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        expression: str,
        pretending: bool,
        voice: str,
    ) -> dict[str, Any]:
        if (
            not expression.strip()
            or len(expression) > 120
            or not voice.strip()
            or len(voice) > 120
            or type(pretending) is not bool
        ):
            raise WorkflowError("Record only your actual own expression, voice and presentation")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            if (
                state.revision != expected
                or state.sheets[actor.entity].girl != "AM"
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Reopen the actual original AM's current presentation")
            if expression.strip().casefold() != "smile":
                rules.require_freedom(state, actor, "expression")
            if pretending:
                rules.require_freedom(state, actor, "pretend_girl")
            event = str(uuid4())
            state.facts.append(
                dict(
                    kind="am_presentation",
                    actor=actor.model_dump_json(),
                    event=event,
                    expression=expression.strip(),
                    voice=voice.strip(),
                    pretending="true" if pretending else "false",
                )
            )
            self.game.event(c, viewer.user_id, key, "m3.am_presentation", state, event_id=event)
            return dict(presentation=rules.presentation(state, actor))

        return self.store._write(
            viewer,
            key,
            "m3.am_presentation",
            dict(expected=expected, expression=expression, pretending=pretending, voice=voice),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )


def pilot_order_authority(
    game: GameService, c: Connection, state: GameState, issuer: int, target: int
) -> dict[str, Any] | None:
    """Actual native Pilot's target-scoped authority from this original AM's secret."""
    first, second = current_ref(state, issuer), current_ref(state, target)
    candidates = [
        x
        for x in rules.discoveries(state)
        if x.discoverer == first
        and x.actor == second
        and first.kind == "pilot"
        and rules.holds_secret(state, x)
    ]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise WorkflowError("Recover the exact original Pilot/AM secret authority")
    registry = Access(game.store).registry
    assert registry is not None
    registry.require_available(rules.RULE)
    value = secret_authority(game, c, state, first, second)
    return dict(
        discovery=value.id,
        secret_event=value.secret_event,
        issuer=first.model_dump(mode="json"),
        target=second.model_dump(mode="json"),
    )


def valid_pilot_order(
    game: GameService, c: Connection, state: GameState, row: dict[str, Any]
) -> bool:
    frozen = json.loads(row["body_json"]).get("am_secret")
    if frozen is None:
        return False
    actual = pilot_order_authority(game, c, state, int(row["issuer_id"]), int(row["target_id"]))
    if actual is None or actual != frozen:
        raise WorkflowError(
            "AM_SECRET_EXPIRED: preserve the actual original issuer, AM and kept secret"
        )
    return True


def validate_pending_pilot_damage(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorRef,
    asset_id: str | None,
    event: str,
    actor: ActorRef | None,
    chooser_controller: int | None,
) -> rules.Discovery:
    """Positive current source before real damage; canonical proof is separate afterward."""
    from girlframe.services.m3_dose_up import _roll_source

    value = source(game, c, state, action["data"]["am_scrutinized"]["discovery"])
    _actual(game, c, state, value)
    _roll_source(game, c, action)
    meta = action["data"]["am_scrutinized"].get("pilot_damage", {})
    staged = action["data"].get("choices", {}).get(f"am_pilot_damage:{value.caster}", {})
    rows, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    if (
        not _native_discoverer(state, value, profiles(c, game.store.campaign_id))
        or target != value.discoverer
        or actor != value.actor
        or chooser_controller != value.caster
        or value.action != action["id"]
        or value.outcome != "violence"
        or meta.get("phase") != "select"
        or action["data"].get("response_event") != event
        or staged.get("options") != [asset_id]
        or "violence" not in allowed(game, c, state, value)
        or not any(
            x.id == asset_id
            for x in pilot_damage_assets(state, target, profiles(c, game.store.campaign_id))
        )
        or not c.scalar(
            sa.select(rows.c.id).where(
                rows.c.campaign_id == game.store.campaign_id,
                rows.c.action_id == action["id"],
                rows.c.actor_id == str(value.caster),
                rows.c.kind == "am_pilot_damage",
                rows.c.state == "answered",
                ~sa.exists(
                    sa.select(responses.c.event_id).where(
                        responses.c.campaign_id == rows.c.campaign_id,
                        responses.c.choice_id == rows.c.id,
                    )
                ),
            )
        )
    ):
        raise WorkflowError(
            "Prove the actual AM's presently applied damage choice and original Girl"
        )
    return value


def _pilot_damage_proof(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> rules.Discovery:
    value = source(game, c, state, action["data"]["am_scrutinized"]["discovery"])
    details = action["data"]["am_scrutinized"].get("pilot_damage", {})
    if (
        value.discoverer.kind != "pilot"
        or value.outcome != "violence"
        or details.get("target") != value.discoverer.model_dump(mode="json")
        or not details.get("damage_event")
    ):
        raise WorkflowError("Recover actual original Pilot damage and its own response")
    original = _history(game, c, details["damage_event"])
    applied = any(
        x.get("kind") == "battle_damage_stage"
        and x.get("event") == details["damage_event"]
        and x.get("applied") == value.discoverer.model_dump_json()
        and x.get("asset") == details.get("asset")
        for x in original.facts
    )
    deferred = False
    for fact in original.facts:
        if (
            fact.get("kind") != "battle_damage_stage"
            or fact.get("event") != details["damage_event"]
            or fact.get("source_action") != action["id"]
            or not fact.get("requirement")
        ):
            continue
        requirement = json.loads(fact["requirement"])
        if requirement.get("kind") != "sprite_intercept":
            continue
        blow = json.loads(requirement["details"]["blow"])
        if (
            blow.get("target") == value.discoverer.model_dump(mode="json")
            and blow.get("asset") == details.get("asset")
            and blow.get("source_action") == action["id"]
            and blow.get("source_event") == details["damage_event"]
            and blow.get("occurrence") == "am_scrutinized_pilot"
            and fact.get("id") in details["work"]
        ):
            deferred = True
    if not (applied or deferred):
        raise WorkflowError("Recover the actual damaged Asset or its exact pending interception")
    responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
    answered = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == details["damage_event"],
            choices.c.action_id == action["id"],
            choices.c.kind == "am_pilot_damage",
            responses.c.actor_id == str(value.caster),
        )
    )
    if answered is None or json.loads(answered).get("options") != [details.get("asset")]:
        raise WorkflowError("Recover the original AM's actual Asset choice")
    return value


def apply_pilot_damage(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    value = source(game, c, state, action["data"]["am_scrutinized"]["discovery"])
    meta = action["data"]["am_scrutinized"]
    details = meta.get("pilot_damage", {})
    event = action["data"]["response_event"]
    if (
        value.discoverer.kind != "pilot"
        or value.outcome != "violence"
        or answer.denied
        or answer.fields
        or answer.flag is not None
        or answer.member is not None
        or answer.number is not None
        or not answer.text.strip()
        or len(answer.text) > 1200
    ):
        raise WorkflowError("Use the actual original Pilot's source-owned damage/response")
    if request["kind"] == "am_pilot_damage":
        actual = resolve(state, value.discoverer, profiles(c, game.store.campaign_id))
        if (
            details.get("phase") != "select"
            or len(answer.options) != 1
            or not any(x.id == answer.options[0] and not x.damaged for x in actual.assets)
        ):
            raise WorkflowError("The original AM chooses one actual intact operator Asset")
        chosen = next(x for x in actual.assets if x.id == answer.options[0])
        if (
            chosen.family == "frame"
            and not any(
                x.family == "frame" and not x.damaged and x.id != chosen.id for x in actual.assets
            )
            and not (
                actual.piloting is True
                and actual.inside_frame is True
                and actual.occupied_frame_instance == actual.frame_instance
            )
        ):
            raise WorkflowError(
                "SOURCE_FRAME_CONSEQUENCE_REQUIRED: preserve actual battle/Frame exhaustion context"
            )
        from girlframe.services.m3_battle import damage_actor

        # The trusted consumer rereads this real Action. Keep the current owned answer in
        # the same atomic transaction; its canonical response/event are still written by Game.
        game.save_action(c, action)
        changed, work = damage_actor(
            game,
            c,
            state,
            target=value.discoverer,
            asset_id=answer.options[0],
            source_action=action["id"],
            source_work=None,
            event=event,
            actor=value.actor,
            opponent=value.actor,
            chooser_controller=value.caster,
            occurrence="am_scrutinized_pilot",
            physical_blow=True,
        )
        _copy(state, changed)
        details.update(
            asset=answer.options[0],
            damage_event=event,
            work=list(work),
            phase="work" if work else "response",
        )
        if not work:
            game.request(c, action, value.controller, "am_pilot_response")
        return
    if request["kind"] == "am_pilot_response":
        _pilot_damage_proof(game, c, state, action)
        if details.get("phase") != "response" or answer.options:
            raise WorkflowError("The original operator answers only after actual damage work")
        details.update(phase="answered", response_event=event)
        action["data"]["result"]["am_operator_response"] = dict(
            actor=value.discoverer.model_dump(mode="json"), text=answer.text
        )
        _finish(game, c, state, action)
        return
    raise WorkflowError("Complete the actual required damage work through its owner controls")


def pilot_defeat_projection(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    from girlframe.services.m3_battle import source_parent_for_defeat

    value = _pilot_damage_proof(game, c, state, action)
    details = action["data"]["am_scrutinized"]["pilot_damage"]
    body = json.loads(row["body_json"])
    table = t.m3["m3_required_work"]
    work = (
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == body.get("work_id"),
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if (
        row["kind"] != "battle_defeat"
        or row["action_id"] != action["id"]
        or row["actor_id"] != str(value.controller)
        or row["state"] != "pending"
        or details["phase"] != "work"
        or body.get("work_id") not in details["work"]
        or work is None
        or work["kind"] != "defeat"
        or work["state"] != "pending"
        or work["owner_id"] != value.discoverer.entity
        or source_parent_for_defeat(game, c, dict(work), value.discoverer) != action["id"]
    ):
        raise WorkflowError("Open only this original Girl's actual source-bound Frame Defeat")
    return dict(
        am_damage_defeat=True,
        parent=action["id"],
        actor=value.controller,
        channel=int(action["channel_id"]),
        body=body,
        play="defeat",
        result={},
    )


def complete_pilot_damage(
    game: GameService,
    c: Connection,
    row: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    body = json.loads(row["body_json"])
    action = game.action(c, body["source_action"])
    state = load_state(c, game.store.campaign_id)
    value = _pilot_damage_proof(game, c, state, action)
    details = action["data"]["am_scrutinized"]["pilot_damage"]
    if row["id"] not in details["work"] or row["state"] != "resolved":
        raise WorkflowError("Only this actual original damage work advances its human response")
    if details["phase"] != "work":
        return
    work_table = t.m3["m3_required_work"]
    for identity in details["work"]:
        status = c.scalar(
            sa.select(work_table.c.state)
            .where(work_table.c.campaign_id == game.store.campaign_id, work_table.c.id == identity)
            .order_by(work_table.c.revision.desc())
            .limit(1)
        )
        if status != "resolved":
            return
    details["phase"] = "response"
    game.request(c, action, value.controller, "am_pilot_response")
    game.save_action(c, action)
