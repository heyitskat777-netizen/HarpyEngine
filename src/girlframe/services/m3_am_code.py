"""Actual already-knowing NPC maintenance with one real Just Code receipt."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am as scrutiny
from girlframe.engine import m3_am_code as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, higher, shift_status
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_alpha import current
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    actual = Access(game.store)
    actual.authorize(c, viewer, "plays", director_response=True)
    assert actual.registry is not None
    actual.registry.require_available(rules.RULE)


def _prove_maintenance(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Maintenance:
    """Unconditional original contact, knowledge, event and actual effect proofs."""
    from girlframe.services.m3_am_scrutinized import (
        _history,
        _prove_effect,
    )
    from girlframe.services.m3_am_scrutinized import (
        source as discovery_source,
    )

    value = rules.session(state, identity)
    old = rules.session(_history(game, c, value.proposed_event), identity)
    stable = (
        "id",
        "actor",
        "operator",
        "operator_position",
        "operator_vessel",
        "operator_frame",
        "owner",
        "controller",
        "discovery",
        "cast",
        "registry",
        "proposed_event",
        "proposal",
        "position",
        "vessel",
        "frame",
        "cell",
        "order_scope",
        "new_operator",
    )
    if any(getattr(value, x) != getattr(old, x) for x in stable):
        raise WorkflowError("Recover the actual original maintenance participants/body source")
    if value.records_access != old.records_access:
        from girlframe.services.m3_am_records import prove_request_binding

        if (
            old.records_access is not None
            or value.operator.kind != "pilot"
            or not value.records_access
        ):
            raise WorkflowError("Preserve the original intended-record source")
        prove_request_binding(game, c, state, value)
    if value.new_operator:
        if value.discovery:
            raise WorkflowError("Preserve the actual first-time circuit source")
    else:
        known = discovery_source(game, c, state, value.discovery)
        _prove_effect(game, c, known)
        if (
            known.actor != value.actor
            or known.discoverer != value.operator
            or not known.effect_event
        ):
            raise WorkflowError("Use only this actual operator's proved adjustment knowledge")
    events = t.events
    for event, kind, human in (
        (value.proposed_event, "m3.am_code_proposed", value.owner),
        (value.confirmed_event, "m3.am_code_confirmed", value.controller),
    ):
        if event is None:
            continue
        row = c.execute(
            sa.select(events.c.kind, events.c.actor_id).where(
                events.c.campaign_id == game.store.campaign_id, events.c.id == event
            )
        ).first()
        if row is None or row.kind != kind or row.actor_id != str(human):
            raise WorkflowError("Only the original real human source answers establish contact")
    if value.confirmed_event:
        confirmed = rules.session(_history(game, c, value.confirmed_event), identity)
        if (
            confirmed.root != value.root
            or confirmed.confirmation != value.confirmation
            or confirmed.operator_lower != value.operator_lower
            or confirmed.operator_human != value.operator_human
        ):
            raise WorkflowError("Keep the original actually confirmed circuit access/source root")
    if value.order:
        if not value.order_event:
            raise WorkflowError("Recover the actual original operator's Order event")
        issued = rules.session(_history(game, c, value.order_event), identity)
        issuer = c.execute(
            sa.select(events.c.kind, events.c.actor_id).where(
                events.c.campaign_id == game.store.campaign_id, events.c.id == value.order_event
            )
        ).first()
        if (
            issued.order != value.order
            or issued.instruction != value.instruction
            or issued.spoken_words != value.spoken_words
            or issuer is None
            or issuer.kind != "m3.choice_resolved"
            or issuer.actor_id != str(value.controller)
        ):
            raise WorkflowError("Recover the actual original NPC's immutable Order")
    if value.records_access:
        from girlframe.services.m3_am_records import prove as prove_records

        record = prove_records(game, c, state, value.records_access)
        if record.maintenance != value.id or record.learner != value.operator:
            raise WorkflowError("Keep this original operator's actual record source")
    if value.memory_erasure:
        from girlframe.services.m3_am_memory import prove as prove_memory

        prove_memory(game, c, state, value.memory_erasure)
    if value.backup:
        from girlframe.services.m3_am_backup import prove as prove_backup

        prove_backup(game, c, state, value.backup)
    if value.body_swap:
        from girlframe.services.m3_am_body import prove as prove_body

        prove_body(game, c, state, value.body_swap)
    if value.branch:
        from girlframe.services.m3_am_branch import prove as prove_branch

        prove_branch(game, c, state, value.branch)
    return value


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Maintenance:
    value = _prove_maintenance(game, c, state, identity)
    if value.new_discovery:
        prove_code_discovery(game, c, state, game.action(c, value.action or ""))
    return value


def actual(game: GameService, c: Connection, state: GameState, value: rules.Maintenance) -> None:
    if value.new_operator:
        access_source = Access(game.store)
        assert access_source.registry is not None
        access_source.registry.require_available(scrutiny.RULE)
        if not value.new_discovery and any(
            x.actor == value.actor and x.discoverer == value.operator and x.phase != "declined"
            for x in scrutiny.discoveries(state)
        ):
            raise WorkflowError("KNOWLEDGE_CHANGED: refresh the actual operator's prior source")
    bound = profiles(c, game.store.campaign_id)
    actor, operator = resolve(state, value.actor, bound), resolve(state, value.operator, bound)
    native_operator = (
        value.operator.kind == "pilot"
        and value.operator != value.actor
        and operator.rules == "girl_frame"
        and operator.controller == int(value.operator.entity)
    )
    if native_operator:
        game.character_binding(c, state, operator.controller)
        if (
            operator.position_sha256 != value.operator_position
            or operator.vessel_id != value.operator_vessel
            or operator.frame_instance != value.operator_frame
            or operator.inside_frame is not False
            or operator.piloting
            or game.immediate_work(c, operator.controller)
        ):
            raise WorkflowError("SOURCE_CONTACT_REQUIRED: preserve the real operator's free body")
    sheet = state.sheets[value.actor.entity]
    physical = next((x for x in state.placements if x.actor == value.actor), None)
    cast = _cast(game, c, state, value.cast.channel)
    body_contact = actor.vessel_id == value.vessel and actor.position_sha256 == value.position
    if value.body_swap:
        from girlframe.engine.m3_am_body import connection, swap

        changed = swap(state, value.body_swap)
        body_contact = (
            not changed.returned_event
            and physical == changed.active_pose
            and connection(state, changed.id).connected
        )
    if (
        actor.girl != "AM"
        or value.actor.kind != "pilot"
        or not (native_operator or value.operator.kind == "npc" and operator.rules == "npc")
        or operator.controller != value.controller
        or (not native_operator and state.handler != value.controller)
        or any(x.active for x in state.director_contexts)
        or game.store.policy.m3_approval is None
        or value.registry != game.store.policy.m3_approval.registry_sha256
        or cast.adjudicator is not None
        or fingerprint(cast) != fingerprint(value.cast)
        or actor.cell != value.cell
        or operator.cell != value.cell
        or actor.inside_frame is not False
        or actor.piloting
        or actor.custody
        or operator.custody
        or not body_contact
        or actor.frame_instance != value.frame
        or physical is None
        or not physical.vitals_active
        or physical.incapacitated
        or not has_rule(sheet, rules.RULE, "AM")
        or sheet.medical_state != "fit"
    ):
        raise WorkflowError(
            "SOURCE_CONTACT_REQUIRED: use the actual unchanged free bodies/circuit access"
        )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    access(game, c, viewer)
    state = load_state(c, game.store.campaign_id)
    meta = action["data"]["am_code"]
    value = source(game, c, state, meta["maintenance"])
    actual(game, c, state, value)
    record_answer = False
    if value.records_access:
        from girlframe.services.m3_am_records import prove as prove_records

        record = prove_records(game, c, state, value.records_access)
        choices = t.m2["m2_choices"]
        record_answer = bool(
            record.gm == viewer.user_id
            and record.question_event
            and record.phase == "granted"
            and c.scalar(
                sa.select(choices.c.id).where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.action_id == action["id"],
                    choices.c.actor_id == str(viewer.user_id),
                    choices.c.kind == "am_code_records_answer",
                    choices.c.state == "pending",
                )
            )
        )
    if value.action != action["id"] or (viewer.user_id not in meta["table"] and not record_answer):
        raise WorkflowError("Only the actual source table or its owed original Handler answers")


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    access(game, c, viewer)
    value = source(game, c, state, prepared.source_work or "")
    actual(game, c, state, value)
    if (
        value.phase != "ready"
        or viewer.user_id != value.owner
        or channel != value.cast.channel
        or prepared.parent != value.root
        or prepared.target_actor != value.operator
        or prepared.target is not None
        or prepared.order_id
        or prepared.off_duty_id
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
    ):
        raise WorkflowError("Use the actual owner-confirmed identity-maintenance source only")
    from girlframe.services.m3_am_records import ready as records_ready

    records_ready(game, c, state, value)
    return dict(
        maintenance=value.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.operator.model_dump(mode="json"),
        cast=value.cast.model_dump(mode="json"),
        cast_sha256=fingerprint(value.cast),
        table=sorted({x.controller for x in value.cast.roles} | {value.controller}),
        phase="unrolled",
    )


def bind(state: GameState, action: dict[str, Any]) -> None:
    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    if value.phase != "ready" or value.action:
        raise WorkflowError("This real maintenance already has its original source roll")
    rules.put(state, value.model_copy(update=dict(phase="active", action=action["id"])))


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    tier = action["data"]["result"]["tier"]
    if tier == "high":
        if value.new_operator:
            from girlframe.engine.m3_handler_consequences import active_handler

            event = action["data"]["response_event"]
            assert state.handler is not None
            identity = str(uuid4())
            discovered = scrutiny.Discovery(
                id=identity,
                code_origin=value.id,
                actor=value.actor,
                discoverer=value.operator,
                controller=value.controller,
                caster=value.owner,
                cast=value.cast,
                registry=value.registry,
                proposed_event=event,
                proposal="Actual final high Just Code reveals the adjustment",
                confirmed_event=event,
                confirmation=value.confirmation,
                phase="active",
                lower_status=value.operator_lower,
                human=value.operator_human,
                handler=active_handler(state),
                handler_controller=state.handler,
                action=action["id"],
                root_action=value.root,
            )
            scrutiny.put(state, discovered)
            value = value.model_copy(update=dict(new_discovery=identity))
            rules.put(state, value)
            action["data"]["am_scrutinized"] = dict(
                discovery=identity,
                actor=value.actor.model_dump(mode="json"),
                target=value.operator.model_dump(mode="json"),
                caster=value.owner,
                discoverer_controller=value.controller,
                handler_controller=state.handler,
                cast=value.cast.model_dump(mode="json"),
                cast_sha256=fingerprint(value.cast),
                table=sorted({x.controller for x in value.cast.roles} | {value.controller}),
                phase="code_effects",
                followups=[],
                code_origin=value.id,
            )
        else:
            shift_status(state, value.owner, -1)
    game.request(
        c,
        action,
        value.controller,
        "am_code_order" if tier == "low" else "am_code_options",
    )


def finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine
    from girlframe.services.m3_am_body_consequences import intercept_finish

    if intercept_finish(game, c, state, action, event):
        return
    if game.pending(c, action["id"]):
        return
    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    if value.records_access:
        from girlframe.engine.m3_am_records import access as record_access
        from girlframe.services.m3_am_records import unselected

        if "records" in value.selected_options and action["data"]["result"]["tier"] != "low":
            if record_access(state, value.records_access).phase != "answered":
                raise WorkflowError(
                    "The actual selected Foundation question still requires its answer"
                )
        else:
            unselected(state, value, event)
    if "backup" in value.selected_options and not value.backup:
        raise WorkflowError("The actual selected backup must contain its genuine original snapshot")
    if "body" in value.selected_options and not value.body_swap:
        raise WorkflowError("The selected body option requires its actual physical effect")
    if "branch" in value.selected_options and not value.branch:
        raise WorkflowError("The selected branch requires its actual independent NPC and vessel")
    if value.new_discovery:
        discovery = scrutiny.discovery(state, value.new_discovery)
        if discovery.phase != "complete":
            rules.put(state, value.model_copy(update=dict(phase="active")))
            if discovery.outcome is None:
                game.request(c, action, value.owner, "am_select")
                action["data"]["am_scrutinized"]["phase"] = "choosing"
            return
    rules.put(
        state,
        value.model_copy(update=dict(phase="complete", effect_event=value.effect_event or event)),
    )
    ChoiceEngine(game).finish(c, state, action)


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_am_scrutinized import _copy

    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    event = action["data"]["response_event"]
    if request["kind"] == "am_code_branch":
        from girlframe.services.m3_am_branch import apply as apply_branch

        apply_branch(game, c, state, action, answer)
        finish(game, c, state, action, event)
        return
    if request["kind"] == "am_code_body":
        from girlframe.services.m3_am_body import apply as apply_body

        apply_body(game, c, state, action, answer)
        finish(game, c, state, action, event)
        return
    if request["kind"].startswith("am_code_records_"):
        from girlframe.services.m3_am_records import apply as apply_records

        apply_records(game, c, state, action, request, answer)
        finish(game, c, state, action, event)
        return
    if (
        answer.denied
        or answer.flag is not None
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use the actual original operator/recipient's concrete source response")
    if request["kind"] == "am_code_options":
        options = set(ready_options(value))
        if (
            len(answer.options) > 2
            or len(set(answer.options)) != len(answer.options)
            or not set(answer.options) <= options
            or answer.fields
            or answer.text
        ):
            raise WorkflowError("The actual operator chooses up to two available printed options")
        value = value.model_copy(update=dict(selected_options=answer.options))
        if "backup" in answer.options:
            from girlframe.engine.m3_am_backup import capture

            saved = capture(state, value.id, value.actor, value.operator, action["id"], event)
            value = value.model_copy(update=dict(backup=saved))
        rules.put(state, value)
        if "identities" in answer.options:
            game.request(c, action, value.controller, "am_code_edit")
        if "body" in answer.options:
            game.request(c, action, value.controller, "am_code_body")
        if "branch" in answer.options:
            game.request(c, action, value.controller, "am_code_branch")
        if "records" in answer.options:
            from girlframe.services.m3_am_records import grant

            grant(state, value, event)
            game.request(c, action, value.controller, "am_code_records_question")
        finish(game, c, state, action, event)
        return
    if request["kind"] == "am_code_edit":
        if answer.options != ("edit",) or not answer.text.strip():
            raise WorkflowError("Choose the actual rewrite (or zero replacements) and describe it")
        scope = answer.fields.get("memory_scope", "none")
        if scope not in ("none", "selected", "all"):
            raise WorkflowError("Choose no erasure, selected memories, or all prior memories")
        from typing import cast

        from girlframe.engine.m3_am_memory import Scope

        _copy(
            state,
            rules.rewrite(
                state,
                value.id,
                {k: v for k, v in answer.fields.items() if k not in ("memory_scope", "memories")},
                event,
                memory_scope=cast(Scope, scope),
                memories=answer.fields.get("memories", ""),
            ),
        )
    elif request["kind"] == "am_code_order":
        if answer.options or answer.fields or not answer.text.strip() or len(answer.text) > 1180:
            raise WorkflowError("The actual operator chooses the real words to be spoken")
        command = "Say exactly: " + answer.text.strip()
        identity = str(uuid4())
        c.execute(
            t.m2["m2_orders"]
            .insert()
            .values(
                campaign_id=game.store.campaign_id,
                id=identity,
                issuer_id=value.operator.entity,
                target_id=str(value.owner),
                channel_id=str(value.cast.channel),
                state="awaiting_response",
                body_json=json.dumps(
                    dict(
                        text=command,
                        spoken_words=answer.text.strip(),
                        order_scope=value.order_scope,
                        am_code=value.id,
                        issuer=value.operator.model_dump(mode="json"),
                        target=value.actor.model_dump(mode="json"),
                        source_action=action["id"],
                        source_event=event,
                        irresistible=True,
                    )
                ),
            )
        )
        rules.put(
            state,
            value.model_copy(
                update=dict(
                    order=identity,
                    order_event=event,
                    instruction=command,
                    spoken_words=answer.text.strip(),
                )
            ),
        )
        action["data"]["order_id"] = identity
        game.request(c, action, value.owner, "am_code_obey")
        return
    elif request["kind"] == "am_code_obey":
        if (
            len(answer.options) != 1
            or answer.options[0] not in rules.FOLLOW
            or answer.fields
            or answer.text.strip() != value.spoken_words
        ):
            raise WorkflowError(
                "Disobey is unavailable: record your own actual matching spoken words and behavior"
            )
        order = t.m2["m2_orders"]
        row = (
            c.execute(
                sa.select(order).where(
                    order.c.campaign_id == game.store.campaign_id, order.c.id == value.order
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["state"] != "awaiting_response"
            or row["issuer_id"] != value.operator.entity
            or row["target_id"] != str(value.owner)
            or json.loads(row["body_json"]).get("source_action") != action["id"]
            or json.loads(row["body_json"]).get("source_event") != value.order_event
            or json.loads(row["body_json"]).get("text") != value.instruction
            or json.loads(row["body_json"]).get("am_code") != value.id
            or json.loads(row["body_json"]).get("spoken_words") != value.spoken_words
            or json.loads(row["body_json"]).get("order_scope") != "spoken_statement"
        ):
            raise WorkflowError("Recover the actual original irresistible NPC Order")
        c.execute(
            order.update()
            .where(order.c.campaign_id == game.store.campaign_id, order.c.id == value.order)
            .values(state="followed")
        )
        state.facts.append(
            dict(
                kind="am_code_actual_spoken_statement",
                maintenance=value.id,
                actor=value.actor.model_dump_json(),
                order=value.order or "",
                event=event,
                behavior=answer.options[0],
                account=answer.text,
            )
        )
        rules.put(
            state,
            value.model_copy(
                update=dict(phase="complete", performance=answer.text, effect_event=event)
            ),
        )
    else:
        raise WorkflowError("Complete the exact actual circuit-maintenance source")
    finish(game, c, state, action, event)


def projection(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    details: dict[str, Any] = {}
    if request["kind"] == "am_code_branch":
        from girlframe.services.m3_am_branch import projection as project_branch

        details["branch"] = project_branch(game, c, state, value)
    if request["kind"] == "am_code_body":
        from girlframe.services.m3_am_body import projection as project_body

        details["body"] = project_body(game, c, state, value)
    if request["kind"].startswith("am_code_records_"):
        from girlframe.services.m3_am_records import projection as project_records

        details["records"] = project_records(game, c, state, value, request["kind"])
        details["records_id"] = value.records_access
    return dict(
        **details,
        available_options=ready_options(value),
        maintenance=value.id,
        identities=[x.model_dump(mode="json") for x in rules.choices(state, value.actor)],
        instruction=value.instruction,
        spoken_words=value.spoken_words,
        actor=state.sheets[value.actor.entity].callsign,
        behavior=rules.FOLLOW,
    )


def ready_options(value: rules.Maintenance) -> tuple[str, ...]:
    return ("identities", "backup", "body", "branch") + (
        ("records",) if value.records_access else ()
    )


def _operator_contact(operator: Any) -> dict[str, Any]:
    return (
        dict(
            operator_position=operator.position_sha256,
            operator_vessel=operator.vessel_id,
            operator_frame=operator.frame_instance,
        )
        if operator.ref.kind == "pilot"
        else {}
    )


def unknown_operators(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer, channel: int
) -> list[dict[str, Any]]:
    from girlframe.engine.m3_actor_bonds import current_ref

    sheet = state.sheets.get(str(viewer.user_id))
    if sheet is None or sheet.girl != "AM" or state.world is None:
        return []
    registry = Access(game.store).registry
    assert registry is not None
    try:
        registry.require_available(scrutiny.RULE)
    except ValueError:
        return []
    actor = current_ref(state, viewer.user_id)
    own = resolve(state, actor, profiles(c, game.store.campaign_id))
    cast = _cast(game, c, state, channel)
    if cast.adjudicator or any(x.active for x in state.director_contexts) or own.cell is None:
        return []
    result = []
    for role in cast.roles:
        npc = role.actor
        if npc == actor or npc.kind not in ("npc", "pilot"):
            continue
        if npc.kind == "npc" and role.controller != state.handler:
            continue
        if any(
            x.actor == actor and x.discoverer == npc and x.phase != "declined"
            for x in scrutiny.discoveries(state)
        ):
            continue
        try:
            other = resolve(state, npc, profiles(c, game.store.campaign_id))
        except ValueError:
            continue
        native = (
            npc.kind == "pilot"
            and other.rules == "girl_frame"
            and other.controller == role.controller
        )
        if (
            (other.rules == "npc" or native)
            and (
                not native
                or other.inside_frame is False
                and not other.piloting
                and other.position_sha256
                and other.vessel_id
                and other.frame_instance
            )
            and other.alive
            and other.cell == own.cell
            and other.custody in (None, "free")
            and own.inside_frame is False
            and own.custody in (None, "free")
        ):
            result.append(dict(id=npc.token, ref=npc.model_dump(mode="json"), label=other.label))
    return result


def prove_code_discovery(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> scrutiny.Discovery:
    """Exact source proof for effective Scrutinized8-10 from an actual Code high."""
    from girlframe.services.m3_am_scrutinized import _history

    meta = action["data"].get("am_scrutinized", {})
    value = scrutiny.discovery(state, meta.get("discovery", ""))
    maintenance = _prove_maintenance(game, c, state, value.code_origin or "")
    born_state = _history(game, c, value.proposed_event)
    born = scrutiny.discovery(born_state, value.id)
    created = rules.session(born_state, maintenance.id)
    proposed = rules.session(_history(game, c, maintenance.proposed_event), maintenance.id)
    stable = (
        "id",
        "code_origin",
        "actor",
        "discoverer",
        "controller",
        "caster",
        "cast",
        "registry",
        "proposed_event",
        "proposal",
        "confirmed_event",
        "confirmation",
        "lower_status",
        "human",
        "handler",
        "handler_controller",
        "action",
        "root_action",
    )
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    final_response = c.scalar(
        sa.select(responses.c.event_id)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == value.proposed_event,
            choices.c.action_id == action["id"],
            choices.c.kind.in_(
                (
                    "tag_window",
                    "tag_resolution",
                    "paired_tag",
                    "tag_marker_selection",
                    "tag_marker_agreement",
                )
            ),
        )
    )
    if (
        not proposed.new_operator
        or proposed.discovery
        or not maintenance.new_operator
        or maintenance.new_discovery != value.id
        or created.new_discovery != value.id
        or maintenance.confirmed_event is None
        or maintenance.confirmed_event != created.confirmed_event
        or maintenance.root != created.root
        or maintenance.root != value.root_action
        or maintenance.confirmation != created.confirmation
        or maintenance.confirmation != value.confirmation
        or maintenance.operator_lower != value.lower_status
        or maintenance.operator_human != value.human
        or action["data"].get("play") != rules.PLAY
        or action["data"].get("result", {}).get("tier") != "high"
        or action["data"].get("am_code", {}).get("maintenance") != maintenance.id
        or meta.get("code_origin") != maintenance.id
        or value.action != action["id"]
        or value.actor != maintenance.actor
        or value.discoverer != maintenance.operator
        or value.controller != maintenance.controller
        or value.caster != maintenance.owner
        or final_response is None
        or receipt is None
        or json.loads(receipt) != action["data"].get("receipt")
        or any(getattr(value, key) != getattr(born, key) for key in stable)
    ):
        raise WorkflowError(
            "Recover the actual new-operator high Code receipt and discovery source"
        )
    return value


class CodeService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        discovery: str,
        expected: int,
        account: str,
        *,
        records_subject: ActorRef | None = None,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe actual Identity/memory circuit maintenance")

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_am_scrutinized import _prove_effect
            from girlframe.services.m3_am_scrutinized import source as known_source

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            known = known_source(self.game, c, state, discovery)
            _prove_effect(self.game, c, known)
            cast = _cast(self.game, c, state, known.cast.channel)
            bound = profiles(c, self.store.campaign_id)
            actor, operator = (
                resolve(state, known.actor, bound),
                resolve(state, known.discoverer, bound),
            )
            physical = next((x for x in state.placements if x.actor == known.actor), None)
            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or viewer.user_id != known.caster
                or actor.girl != "AM"
                or not (
                    known.discoverer.kind == "npc"
                    and operator.rules == "npc"
                    and operator.controller == state.handler
                    or known.code_origin
                    and known.discoverer.kind == "pilot"
                    and operator.rules == "girl_frame"
                    and known.discoverer != known.actor
                )
                or cast.adjudicator is not None
                or any(x.active for x in state.director_contexts)
                or actor.cell is None
                or actor.cell != operator.cell
                or actor.inside_frame is not False
                or actor.custody
                or operator.custody
                or not actor.position_sha256
                or not actor.vessel_id
                or not actor.frame_instance
                or physical is None
                or not physical.vitals_active
                or physical.incapacitated
                or not has_rule(state.sheets[known.actor.entity], rules.RULE, "AM")
            ):
                raise WorkflowError(
                    "Use the actual already-knowing NPC and co-present free AM body"
                )
            assert self.store.policy.m3_approval is not None
            event, identity = str(uuid4()), str(uuid4())
            value = rules.Maintenance(
                id=identity,
                actor=known.actor,
                operator=known.discoverer,
                owner=viewer.user_id,
                controller=operator.controller,
                **_operator_contact(operator),
                discovery=discovery,
                cast=cast,
                registry=self.store.policy.m3_approval.registry_sha256,
                proposed_event=event,
                proposal=account,
                position=actor.position_sha256,
                vessel=actor.vessel_id,
                frame=actor.frame_instance,
                cell=actor.cell,
            )
            if records_subject is not None:
                if value.operator.kind == "pilot":
                    raise WorkflowError(
                        "SOURCE_RECORDS_ADAPTER_REQUIRED: separate actual GM dossier delivery"
                    )
                from girlframe.services.m3_am_records import request as request_records

                pointer = request_records(self.game, c, state, value, records_subject, event)
                value = value.model_copy(update=dict(records_access=pointer, selected_options=()))
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_code_proposed",
                state,
                event_id=event,
                maintenance=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.am_code_proposed",
            dict(discovery=discovery, expected=expected, account=account)
            | (
                dict(records_subject=records_subject.model_dump(mode="json"))
                if records_subject
                else {}
            ),
            operation,
            authorize=lambda c: access(self.game, c, viewer),
            auto_audit=False,
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        account: str,
        *,
        records_document: str | None = None,
        records_reference: str | None = None,
        records_complete: bool = False,
        operator_lower: bool | None = None,
        operator_human: bool | None = None,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError(
                "Confirm actual physical circuit access and identity-only maintenance"
            )

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            actual(self.game, c, state, value)
            if (
                state.revision != expected
                or value.phase != "proposed"
                or viewer.user_id != value.controller
                or self.game.pending_actions(c)
            ):
                raise WorkflowError(
                    "Only the original real operator confirms actual circuit access"
                )
            if value.new_operator and value.operator.kind == "pilot":
                actual_human = scrutiny.human_target(state, value.operator)
                actual_lower = higher(state, value.owner, int(value.operator.entity))
                if (
                    operator_lower is not None
                    and operator_lower != actual_lower
                    or operator_human is not None
                    and operator_human != actual_human
                ):
                    raise WorkflowError(
                        "Use the actual Pilot's canonical rank and human classification"
                    )
                value = value.model_copy(
                    update=dict(operator_lower=actual_lower, operator_human=actual_human)
                )
            elif value.new_operator:
                if type(operator_lower) is not bool or type(operator_human) is not bool:
                    raise WorkflowError("Record this actual operator's rank and human-body facts")
                value = value.model_copy(
                    update=dict(operator_lower=operator_lower, operator_human=operator_human)
                )
            elif operator_lower is not None or operator_human is not None:
                raise WorkflowError("Preserve the original known operator's actual source")
            event, identity_root = str(uuid4()), str(uuid4())
            if value.records_access:
                from girlframe.services.m3_am_records import prepare as prepare_records
                from girlframe.services.m3_am_records import prove as prove_records

                if value.operator.kind == "pilot":
                    record = prove_records(self.game, c, state, value.records_access)
                    if (
                        record.phase != "prepared"
                        or records_document is not None
                        or records_reference is not None
                        or records_complete
                    ):
                        raise WorkflowError(
                            "The original Handler prepares the complete dossier separately"
                        )
                else:
                    prepare_records(
                        self.game,
                        c,
                        state,
                        value,
                        event,
                        records_document,
                        records_reference,
                        records_complete,
                    )
            elif records_document is not None or records_reference is not None or records_complete:
                raise WorkflowError("This actual maintenance has no records request")
            scene = self.game.scene(c, value.cast.channel)
            lock = self.game.lock(c, value.cast.channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: finish the actual pending Play")
            table = sorted({x.controller for x in value.cast.roles} | {value.controller})
            data = dict(
                play="am_code_maintenance",
                am_code_source=dict(
                    maintenance=value.id, target=value.operator.model_dump(mode="json")
                ),
                participants=table,
                handler=state.handler,
                character_ids={
                    str(x.controller): x.actor.incarnation
                    for x in value.cast.roles
                    if x.actor.kind == "pilot"
                },
                depth=0,
                receipt=None,
                modifiers=[],
                result={},
                choices={},
            )
            from girlframe.services.m3_recovery import enable

            enable(self.game, c, viewer, data)
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity_root,
                    actor_id=str(value.owner),
                    channel_id=str(value.cast.channel),
                    scene_id=scene["id"],
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data),
                )
            )
            locks = t.m2["m2_locks"]
            changes = dict(
                action_id=identity_root,
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
                        locks.c.channel_id == str(value.cast.channel),
                    )
                    .values(**changes)
                )
            else:
                c.execute(
                    locks.insert().values(
                        campaign_id=self.store.campaign_id,
                        channel_id=str(value.cast.channel),
                        **changes,
                    )
                )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        root=identity_root,
                        phase="ready",
                        confirmed_event=event,
                        confirmation=account,
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_code_confirmed",
                state,
                event_id=event,
                maintenance=value.id,
            )
            return dict(id=value.id, action_id=identity_root)

        return self.store._write(
            viewer,
            key,
            "m3.am_code_confirmed",
            dict(id=identity, expected=expected, account=account)
            | (
                dict(operator_lower=operator_lower, operator_human=operator_human)
                if operator_lower is not None or operator_human is not None
                else {}
            )
            | (
                dict(
                    records_document=records_document,
                    records_reference=records_reference,
                    records_complete=records_complete,
                )
                if records_document is not None or records_reference is not None or records_complete
                else {}
            ),
            operation,
            authorize=lambda c: access(self.game, c, viewer),
            auto_audit=False,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        from girlframe.engine.m3_alpha import current

        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                kind="am_code_source",
                label="Confirm actual Identity/memory circuit maintenance",
                actionable=True,
            )
            for x in rules.sessions(state)
            if x.phase == "proposed"
            and x.controller == viewer.user_id
            and current(state, x.actor)
            and current(state, x.operator)
        ]

    def source_channel(self, viewer: GuildViewer, identity: str) -> int:
        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            value = source(self.game, c, load_state(c, self.store.campaign_id), identity)
            if viewer.user_id not in (value.owner, value.controller):
                raise WorkflowError("This actual maintenance belongs to its original humans")
            return value.cast.channel

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        from girlframe.engine.m3_am_records import access as record_access

        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            scenes = t.m2["m2_scenes"]
            scene_available = (
                c.scalar(
                    sa.select(scenes.c.id).where(
                        scenes.c.campaign_id == self.store.campaign_id,
                        scenes.c.channel_id == str(channel),
                        scenes.c.open.is_(True),
                    )
                )
                is not None
            )
            known = [
                dict(
                    id=x.id,
                    label=resolve(state, x.discoverer, profiles(c, self.store.campaign_id)).label,
                    operator=x.discoverer.model_dump(mode="json"),
                )
                for x in scrutiny.discoveries(state)
                if x.caster == viewer.user_id
                and x.cast.channel == channel
                and x.effect_event
                and x.phase in ("complete", "limited")
                and (x.discoverer.kind == "npc" or x.code_origin and x.discoverer.kind == "pilot")
                and current(state, x.discoverer)
            ]
            values = [
                dict(
                    id=x.id,
                    phase=x.phase,
                    owner=x.owner,
                    controller=x.controller,
                    operator=x.operator.model_dump(mode="json"),
                    new_operator=x.new_operator,
                    operator_response=self.game.action(c, x.action)["data"]
                    .get("result", {})
                    .get("am_operator_response")
                    if x.action
                    else None,
                    proposal=x.proposal,
                    root=x.root,
                    records=x.records_access,
                    records_subject=(
                        record_access(state, x.records_access).label if x.records_access else None
                    ),
                    memory_erasure=x.memory_erasure,
                )
                for x in rules.sessions(state)
                if viewer.user_id in (x.owner, x.controller) and x.cast.channel == channel
            ]
            from girlframe.engine.m3_am_records import records as saved_records
            from girlframe.services.m3_am_records import RecordsService, subjects

            documents = []
            for record in saved_records(state):
                if record.granted_event:
                    learner = resolve(
                        state,
                        record.learner,
                        profiles(c, self.store.campaign_id),
                        require_alive=False,
                    )
                    if learner.controller == viewer.user_id:
                        documents.append(dict(id=record.id, label=record.label))
            from girlframe.engine.m3_am_backup import backups

            saved_backups = [
                dict(id=x.id, captured_revision=x.captured_revision, owner=int(x.actor.entity))
                for x in backups(state)
                if viewer.user_id
                in (
                    rules.session(state, x.maintenance).owner,
                    rules.session(state, x.maintenance).controller,
                )
            ]
            return dict(
                revision=state.revision,
                operators=unknown_operators(self.game, c, state, viewer, channel)
                if scene_available
                else [],
                known=known,
                sessions=values,
                subjects=subjects(self.game, c, state),
                documents=documents,
                records_prepare=RecordsService(self.game)._tasks(c, viewer),
                backups=saved_backups,
            )

    def propose_operator(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        npc: ActorRef,
        expected: int,
        account: str,
        *,
        records_subject: ActorRef | None = None,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe actual first-time circuit access")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or npc.model_dump(mode="json")
                not in [x["ref"] for x in unknown_operators(self.game, c, state, viewer, channel)]
            ):
                raise WorkflowError("Use the actual co-present first-time ordinary NPC operator")
            from girlframe.engine.m3_actor_bonds import current_ref

            actor = current_ref(state, viewer.user_id)
            own = resolve(state, actor, profiles(c, self.store.campaign_id))
            operator = resolve(state, npc, profiles(c, self.store.campaign_id))
            cast = _cast(self.game, c, state, channel)
            assert self.store.policy.m3_approval is not None
            assert (
                own.position_sha256
                and own.vessel_id
                and own.frame_instance
                and own.cell is not None
            )
            event, identity = str(uuid4()), str(uuid4())
            value = rules.Maintenance(
                id=identity,
                actor=actor,
                operator=npc,
                owner=viewer.user_id,
                controller=operator.controller,
                **_operator_contact(operator),
                new_operator=True,
                cast=cast,
                registry=self.store.policy.m3_approval.registry_sha256,
                proposed_event=event,
                proposal=account,
                position=own.position_sha256,
                vessel=own.vessel_id,
                frame=own.frame_instance,
                cell=own.cell,
            )
            actual(self.game, c, state, value)
            if records_subject is not None:
                if value.operator.kind == "pilot":
                    raise WorkflowError(
                        "SOURCE_RECORDS_ADAPTER_REQUIRED: separate actual GM dossier delivery"
                    )
                from girlframe.services.m3_am_records import request as request_records

                pointer = request_records(self.game, c, state, value, records_subject, event)
                value = value.model_copy(update=dict(records_access=pointer, selected_options=()))
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_code_proposed",
                state,
                event_id=event,
                maintenance=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.am_code_new_operator_proposed",
            dict(
                channel=channel, npc=npc.model_dump(mode="json"), expected=expected, account=account
            )
            | (
                dict(records_subject=records_subject.model_dump(mode="json"))
                if records_subject
                else {}
            ),
            operation,
            authorize=lambda c: access(self.game, c, viewer),
            auto_audit=False,
        )
