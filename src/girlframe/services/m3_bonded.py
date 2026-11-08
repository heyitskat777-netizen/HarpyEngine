"""Genuine Pair sources, owned human responses and actual Bonded effects."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, shift_status, tier
from girlframe.engine.m3_actor_bonds import change, current_ref, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _audit, _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("bonded_side", "bonded_mid", "bonded_promise", "bonded_reply", "bonded_high", "bonded_low")


def _copy(state: GameState, other: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(other, name))


def _access(game: GameService, c: Connection, viewer: GuildViewer, rule: str) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rule)


def original_pair(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    required_rule: str = rules.PAIR,
) -> tuple[ActorRef, str]:
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != actor.incarnation
        or not has_rule(sheet, required_rule, "BONDED")
        or sheet.pair is None
    ):
        raise WorkflowError("Use the original current Bonded Girl and actual assigned Pair")
    setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
    if setup is not None and setup.pair is not None:
        original = _history(c, game, setup.source_event).sheets.get(actor.entity)
        if original is None or not original.girl_runtime or original.girl_runtime.setup != setup:
            raise WorkflowError("Recover the immutable actual Pair transition source")
        actual, source = setup.pair, setup.source_event
    else:
        outgoing = next((x for x in sheet.review.bonds if x.outgoing), None)
        if outgoing is None or outgoing.counterpart != sheet.pair:
            raise WorkflowError("Recover the actual reviewed outgoing Pair Bond")
        bond = (
            c.execute(
                sa.select(t.bond_revisions).where(
                    t.bond_revisions.c.campaign_id == game.store.campaign_id,
                    t.bond_revisions.c.id == outgoing.id,
                    t.bond_revisions.c.revision == outgoing.revision,
                )
            )
            .mappings()
            .first()
        )
        if (
            bond is None
            or bond["state"] != "accepted"
            or bond["source_id"] != actor.entity
            or bond["target_id"] != str(sheet.pair)
        ):
            raise WorkflowError("Recover the genuine accepted original Pair Bond")
        histories = c.execute(
            sa.select(t.m2["m2_state_history"].c.body_json)
            .join(
                t.events,
                sa.and_(
                    t.events.c.id == t.m2["m2_state_history"].c.event_id,
                    t.events.c.campaign_id == t.m2["m2_state_history"].c.campaign_id,
                ),
            )
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m2.character_activated",
                t.events.c.actor_id == str(sheet.pair),
            )
            .order_by(t.events.c.seq)
        ).scalars()
        other = next(
            (
                s
                for raw in histories
                if (s := GameState.model_validate_json(raw).sheets.get(str(sheet.pair))) is not None
                and s.source_profile_revision == bond["target_revision"]
            ),
            None,
        )
        if other is None or not other.character_id:
            raise WorkflowError("Activate the actual original Pair; never alias a replacement")
        actual = ActorRef(kind="pilot", entity=str(sheet.pair), incarnation=other.character_id)
        source = bond["event_id"]
    if actual == actor or actual.entity != str(sheet.pair):
        raise WorkflowError("Preserve the distinct actual assigned Pair")
    _native(game, c, state, actor)
    _native(game, c, state, actual)
    return actual, source


def _people(value: rules.Source) -> tuple[ActorRef, ...]:
    values = (
        (value.actor, value.target)
        if value.kind == "sex"
        else (value.actor, value.pair, value.observer)
    )
    return tuple(dict.fromkeys(x for x in values if x is not None))


def _contact(game: GameService, c: Connection, state: GameState, value: rules.Source) -> None:
    cast = _cast(game, c, state, value.cast.channel)
    if fingerprint(cast) != fingerprint(value.cast):
        raise WorkflowError("Recover the unchanged genuine source cast")
    views = {x: _native(game, c, state, x) for x in _people(value)}
    if any(
        v.cell is None
        or v.vessel_id is None
        or value.controllers.get(ref.token) != v.controller
        or value.vessels.get(ref.token) != v.vessel_id
        or not any(r.actor == ref and r.controller == v.controller for r in cast.roles)
        for ref, v in views.items()
    ):
        raise WorkflowError("SOURCE_BODY_REQUIRED: use actual native original bodies and cast")
    if value.kind == "side":
        if not value.apart or any(
            v.custody not in (None, "free") or v.offstage_source for v in views.values()
        ):
            raise WorkflowError("Confirm that these actual original people really are apart")
    elif (
        any(v.inside_frame is not False for v in views.values())
        or len({x.cell for x in views.values()}) != 1
    ):
        raise WorkflowError("Use the actual voluntary original people together here")


def _consents(game: GameService, c: Connection, state: GameState, value: rules.Source) -> None:
    if value.kind != "sex":
        return
    responses = tuple(x for x in rules.records(state, rules.Consent) if x.source == value.id)
    for item in responses:
        if (
            item.person != value.target
            or item.controller != value.controllers[item.person.token]
            or item not in rules.records(_history(c, game, item.event), rules.Consent)
        ):
            raise WorkflowError("Preserve the actual counterpart's voluntary source response")
        _audit(game, c, item.event, ("m3.bonded_confirmed",), item.controller)
    if value.phase not in ("invited", "declined") and (
        len(responses) != 1 or not responses[0].accepted
    ):
        raise WorkflowError("The actual counterpart must confirm their own voluntary intimacy")


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Source:
    value = rules.get(state, identity)
    birth = _history(c, game, value.event)
    born = rules.get(birth, identity)
    stable = (
        "id",
        "kind",
        "actor",
        "pair",
        "target",
        "observer",
        "controllers",
        "vessels",
        "cast",
        "registry",
        "pair_source",
        "apart",
        "event",
        "account",
        "route",
        "delegated_rule",
    )
    if any(getattr(value, k) != getattr(born, k) for k in stable):
        raise WorkflowError("Preserve the genuine original Bonded source and people")
    rule = dict(side=rules.SIDE, intimacy=rules.INTIMACY, sex=rules.SEX)[value.kind]
    actual, source = original_pair(game, c, birth, value.actor, rule)
    if actual != value.pair or source != value.pair_source:
        raise WorkflowError("Preserve the source-time original Pair, not their current account")
    _audit(game, c, value.event, ("m3.bonded_proposed",), int(value.actor.entity))
    _consents(game, c, state, value)
    actions = c.scalars(
        sa.select(t.m2["m2_actions"].c.id).where(
            t.m2["m2_actions"].c.campaign_id == game.store.campaign_id,
            sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.bonded.source") == identity,
        )
    ).all()
    if (
        len(actions) > 1
        or actions
        and value.action != actions[0]
        or value.action is not None
        and value.phase in ("invited", "accepted", "declined")
    ):
        raise WorkflowError("Never clear or rebind an actual confirmed Bonded source")
    if value.action:
        action = game.action(c, value.action)
        meta = action["data"].get("bonded", {})
        bound = rules.get(_history(c, game, value.bound_event or ""), identity)
        if (
            bound.action != value.action
            or str(action["actor_id"]) != value.actor.entity
            or action["scene_id"] != value.cast.id
            or int(action["channel_id"]) != value.cast.channel
            or action["data"]["play"]
            != (rules.SIDE_PLAY if value.kind == "side" else rules.SEX_PLAY)
            or bound.bound_event != value.bound_event
            or meta.get("source") != identity
            or meta.get("actor") != value.actor.model_dump(mode="json")
            or meta.get("pair") != value.pair.model_dump(mode="json")
            or meta.get("cast") != value.cast.model_dump(mode="json")
            or meta.get("target")
            != (value.target.model_dump(mode="json") if value.target else None)
            or meta.get("cast_sha256") != fingerprint(value.cast)
            or action["data"].get("character_ids", {}).get(value.actor.entity)
            != value.actor.incarnation
            or action["data"].get("prepared", {}).get("source_work") != identity
        ):
            raise WorkflowError("Recover the actual confirmed source Play binding")
        if not value.effect_event and any(
            x.source == identity for x in rules.records(state, rules.Selection)
        ):
            raise WorkflowError("Preserve the actual source result before its responses")
        if value.effect_event:
            _, total = _roll_source(game, c, action)
            effect = rules.get(_history(c, game, value.effect_event), identity)
            if value.tier != tier(total) or effect.effect_event != value.effect_event:
                raise WorkflowError("Preserve the real final receipt and source result")
    elif value.effect_event:
        effect = rules.get(_history(c, game, value.effect_event), identity)
        _audit(game, c, value.effect_event, ("m3.bonded_activated",), int(value.actor.entity))
        activation = next(
            (x for x in rules.records(state, rules.Activation) if x.source == identity), None
        )
        if (
            activation is None
            or activation.actor != value.actor
            or activation.event != value.effect_event
            or not activation.account.strip()
            or activation
            not in rules.records(_history(c, game, activation.event), rules.Activation)
        ):
            raise WorkflowError("Preserve the actual performed diceless source and its author")
        if (
            effect.effect_event != value.effect_event
            or effect.tier != value.tier
            or (value.route == "seven" and value.tier != "low")
            or value.route != "seven"
            and value.kind != "intimacy"
        ):
            raise WorkflowError("Unrolled source results never fabricate a Sex receipt")
    for item in rules.records(state, rules.Selection):
        if item.source != identity:
            continue
        saved = next(
            (
                x
                for x in rules.records(_history(c, game, item.event), rules.Selection)
                if x.id == item.id
            ),
            None,
        )
        if (
            saved != item
            or item.person not in _people(value)
            or item.controller != value.controllers[item.person.token]
        ):
            raise WorkflowError("Preserve every original person's immutable owned choice")
        if item.action:
            answer = _response(
                game, c, item.action, item.id, item.event, item.controller, item.kind
            )
            actual_row = (
                c.execute(
                    sa.select(t.m2["m2_choices"]).where(
                        t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_choices"].c.id == item.id,
                    )
                )
                .mappings()
                .one()
            )
            if json.loads(actual_row["body_json"]).get("request") != item.request:
                raise WorkflowError("Preserve the real Pair request and its owned reply")
            if (
                answer.options != item.options
                or answer.denied != item.identities
                or answer.text != item.text
            ):
                raise WorkflowError("Preserve the exact canonical response and source cost")
        else:
            _audit(game, c, item.event, ("m3.bonded_selected",), item.controller)
    for detail in rules.records(state, rules.Detail):
        if detail.source != identity:
            continue
        born_detail = next(
            (
                x
                for x in rules.records(_history(c, game, detail.event), rules.Detail)
                if x.id == detail.id
            ),
            None,
        )
        reply = next(
            (
                x
                for x in rules.records(state, rules.Selection)
                if x.source == identity
                and x.kind == "bonded_reply"
                and x.request == detail.kind
                and x.event == detail.event
                and x.options == ("give",)
            ),
            None,
        )
        if (
            born_detail != detail
            or detail.actor != value.pair
            or detail.target != value.actor
            or detail.controller != value.controllers.get(value.pair.token)
            or reply is None
            or detail.account != _text(reply.text).get("content", _text(reply.text)["account"])
        ):
            raise WorkflowError(
                "Preserve the real Pair-authored secret, Order or appearance source"
            )
    for binding in rules.records(state, rules.OrderBinding):
        if binding.source != identity:
            continue
        born_binding = next(
            (
                x
                for x in rules.records(_history(c, game, binding.event), rules.OrderBinding)
                if x.id == binding.id
            ),
            None,
        )
        binding_detail = next(
            (x for x in rules.records(state, rules.Detail) if x.id == binding.detail), None
        )
        order = (
            c.execute(
                sa.select(t.m2["m2_orders"]).where(
                    t.m2["m2_orders"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_orders"].c.id == binding.order,
                )
            )
            .mappings()
            .first()
        )
        if (
            born_binding != binding
            or binding_detail is None
            or order is None
            or order["issuer_id"] != binding.actor.entity
            or order["target_id"] != binding.target.entity
            or (binding.actor, binding.target) != (binding_detail.actor, binding_detail.target)
            or json.loads(order["body_json"]).get("text") != binding_detail.account
        ):
            raise WorkflowError(
                "Preserve the actual requested Order row and original issuer/recipient"
            )
    if (
        value.phase == "complete"
        and value.kind == "sex"
        and value.tier == "mid"
        and not _ready_to_close(state, value)
    ):
        raise WorkflowError("Complete each actual Pair reply and genuine Order before closing")
    if value.phase == "complete":
        if not value.completed_event:
            raise WorkflowError("Preserve the actual completed source event")
        completed = rules.get(_history(c, game, value.completed_event), identity)
        if completed.completed_event != value.completed_event or completed.phase != "complete":
            raise WorkflowError("Preserve real completion, never a mutable acknowledgment")
    for help_record in rules.records(state, rules.PairHelp):
        if help_record.source != identity:
            continue
        if (
            help_record.actor != value.actor
            or help_record.pair != value.pair
            or help_record.controller != int(value.pair.entity)
            or help_record
            not in rules.records(_history(c, game, help_record.event), rules.PairHelp)
        ):
            raise WorkflowError("Preserve the original Pair's actual help source")
        _audit(game, c, help_record.event, ("m3.bonded_helped",), help_record.controller)
    return value


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    rule = rules.SIDE if prepared.play == rules.SIDE_PLAY else rules.SEX
    _access(game, c, viewer, rule)
    value = prove(game, c, state, prepared.source_work or "")
    expected = rules.SIDE_PLAY if value.kind == "side" else rules.SEX_PLAY
    if (
        prepared.play != expected
        or value.kind == "intimacy"
        or value.route != "pair"
        or value.phase != "accepted"
        or value.actor != current_ref(state, viewer.user_id)
        or channel != value.cast.channel
        or prepared.target is not None
        or prepared.target_actor is not None
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
    ):
        raise WorkflowError("Use the genuine accepted original Bonded source")
    _contact(game, c, state, value)
    handler = active_handler(state)
    if handler is None or value.cast.facilitator is None:
        raise WorkflowError("Recover the actual original Handler and source table")
    return dict(
        source=value.id,
        actor=value.actor.model_dump(mode="json"),
        pair=value.pair.model_dump(mode="json"),
        target=value.target.model_dump(mode="json") if value.target else None,
        cast=value.cast.model_dump(mode="json"),
        cast_sha256=fingerprint(value.cast),
        table=sorted({x.controller for x in value.cast.roles} | {value.cast.facilitator}),
        handler=handler.model_dump(mode="json"),
        handler_controller=resolve(
            state, handler, profiles(c, game.store.campaign_id), require_current_profile=False
        ).controller,
    )


def bind(state: GameState, action: dict[str, Any], event: str | None = None) -> None:
    value = rules.get(state, action["data"]["bonded"]["source"])
    if not event or value.action or value.phase != "accepted":
        raise WorkflowError("Bind the genuine source once to the actual confirmed Play")
    rules.put(
        state, value.model_copy(update=dict(action=action["id"], bound_event=event, phase="bound"))
    )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    value = rules.get(load_state(c, game.store.campaign_id), action["data"]["bonded"]["source"])
    _access(game, c, viewer, rules.SIDE if value.kind == "side" else rules.SEX)
    if viewer.user_id not in action["data"]["bonded"]["table"]:
        raise WorkflowError("Only the original source table owns this response")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    value = prove(game, c, state, action["data"]["bonded"]["source"])
    if value.phase != "bound" or value.actor != current_ref(state, viewer.user_id):
        raise WorkflowError("Resume the saved source without another roll")
    _contact(game, c, state, value)


def sex_parties(state: GameState, action: dict[str, Any]) -> tuple[ActorRef, ...]:
    value = rules.get(state, action["data"]["bonded"]["source"])
    return (value.actor, value.target) if value.target is not None and value.kind == "sex" else ()


def _pending(game: GameService, c: Connection, action: dict[str, Any], value: rules.Source) -> None:
    if value.kind == "side":
        game.request(c, action, int(value.actor.entity), "bonded_side", {})
    else:
        kind = (
            "bonded_mid"
            if value.tier == "mid"
            else "bonded_promise"
            if value.tier == "high"
            else "bonded_low"
        )
        person = value.actor if value.tier in ("mid", "high") else value.target
        assert person is not None
        game.request(c, action, value.controllers[person.token], kind, {})


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.get(state, action["data"]["bonded"]["source"])
    if value.effect_event:
        raise WorkflowError("Resume the original Bonded result without duplicating it")
    if value.kind == "sex":
        from girlframe.services.m3_gender_designation import offer_animal_tags

        if offer_animal_tags(game, c, state, action):
            action["data"]["gender_sex_deferred"] = True
            return
    _, total = _roll_source(game, c, action)
    event = action["data"]["response_event"]
    value = value.model_copy(update=dict(effect_event=event, tier=tier(total), phase="results"))
    rules.put(state, value)
    if value.kind == "side" and value.tier == "low":
        shift_status(state, int(value.actor.entity), 1)
    if value.kind == "sex" and value.tier == "mid":
        _copy(state, set_depth(state, value.actor, value.pair, 2, event))
    _pending(game, c, action, value)


def _text(text: str) -> dict[str, str]:
    try:
        value = json.loads(text)
    except ValueError:
        value = {"account": text}
    if (
        not isinstance(value, dict)
        or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items())
        or not value.get("account", "").strip()
        or len(text) > 7000
    ):
        raise WorkflowError("Author your own actual account and source fields")
    return value


def _give(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Source,
    giver: ActorRef,
    target: ActorRef,
    label: str,
    event: str,
    suffix: str,
) -> None:
    _copy(
        state,
        give_tag(
            state,
            profiles(c, game.store.campaign_id),
            target,
            giver,
            label,
            value.id + ":" + suffix + ":" + event,
            event,
            tuple(sorted(set(value.controllers.values()))),
        ),
    )


def _complete(state: GameState, value: rules.Source, event: str) -> rules.Source:
    updated = value.model_copy(update=dict(phase="complete", completed_event=event))
    rules.put(state, updated)
    return updated


def _detail(state: GameState, value: rules.Source, kind: str, account: str, event: str) -> None:
    assert value.target is not None
    rules.put(
        state,
        rules.Detail.model_validate(
            dict(
                id=value.id + ":" + kind,
                source=value.id,
                kind=kind,
                actor=value.pair,
                target=value.actor,
                controller=value.controllers[value.pair.token],
                account=account,
                event=event,
            )
        ),
    )


def _choice_person(value: rules.Source, kind: str) -> ActorRef:
    if kind in ("bonded_side", "bonded_mid", "bonded_promise", "bonded_intimacy"):
        return value.actor
    assert value.target is not None
    return value.target


def _select(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Source,
    kind: str,
    answer: ChoiceAnswer,
    event: str,
    identity: str,
    action: dict[str, Any] | None,
    request: str | None = None,
) -> None:
    if (
        answer.fields
        or answer.flag is not None
        or answer.member is not None
        or answer.number is not None
    ):
        raise WorkflowError("Use only this actual owned Bonded response shape")
    if answer.denied and kind not in ("bonded_mid", "bonded_high", "bonded_low"):
        raise WorkflowError("This result has no private Identity or Tag selector")
    fields = _text(answer.text)
    options = answer.options
    person = _choice_person(value, kind)
    if value.phase != "results" or len(set(options)) != len(options):
        raise WorkflowError("Choose the actual saved source result once")
    valid = projection_options(state, value, kind)
    if any(x not in valid for x in options):
        raise WorkflowError("Select only actual available printed outcomes")
    selection = rules.Selection(
        id=identity,
        source=value.id,
        action=action["id"] if action else None,
        person=person,
        controller=value.controllers[person.token],
        kind=kind,
        options=options,
        identities=answer.denied,
        request=request,
        text=answer.text,
        event=event,
    )
    if kind == "bonded_side":
        if (
            len([x for x in options if x in ("stay", "arrive")]) != 1
            or value.tier == "high"
            and "arrive" not in options
            or "weapon" in options
            and (value.tier != "high" or "arrive" not in options)
        ):
            raise WorkflowError("Choose the actual printed stay or arrival result")
        if "weapon" in options and (
            not fields.get("weapon_name", "").strip()
            or not fields.get("weapon_description", "").strip()
        ):
            raise WorkflowError("Describe the actual weapon you needed and found")
        rules.put(state, selection)
        if "arrive" in options:
            from girlframe.services.m3_bonded_support import arrive

            arrive(game, c, state, value, event, fields["account"], weapon="weapon" in options)
        elif not fields.get("question", "").strip():
            raise WorkflowError("Ask your Pair when she is coming for you")
        _complete(state, value, event)
    elif kind == "bonded_mid":
        if len(answer.denied) != len(options) or len(set(answer.denied)) != len(answer.denied):
            raise WorkflowError("Unmark one distinct actual marked Identity for each chosen option")
        sheet = state.sheets[value.actor.entity]
        marked = {
            x.id: x for x in sheet.identities if x.marked and x.id not in sheet.sedation_locked
        }
        if any(x not in marked for x in answer.denied):
            raise WorkflowError("Choose actual marked Identities available to unmark")
        for entry in answer.denied:
            marked[entry].marked = False
        rules.put(state, selection)
        if action is None:
            raise WorkflowError("Use the actual rolled Pair Sex request source")
        for option in options:
            game.request(
                c, action, value.controllers[value.pair.token], "bonded_reply", {"request": option}
            )
        if not options:
            _complete(state, value, event)
    elif kind == "bonded_reply":
        if (
            request not in ("tag", "secret", "order", "appearance")
            or len(options) != 1
            or answer.denied
        ):
            raise WorkflowError("Reply only to this actual requested shaping action")
        asked = next(
            (
                x
                for x in rules.records(state, rules.Selection)
                if x.source == value.id and x.kind == "bonded_mid"
            ),
            None,
        )
        if (
            asked is None
            or request not in asked.options
            or any(
                x.source == value.id and x.kind == kind and x.request == request
                for x in rules.records(state, rules.Selection)
            )
        ):
            raise WorkflowError("Preserve the original question and one actual Pair response")
        if options == ("give",):
            content = fields.get("content", fields["account"])
            if not content.strip():
                raise WorkflowError("The actual Pair authors their own performed reply")
            if request == "tag":
                _give(
                    game, c, state, value, value.pair, value.actor, content, event, "requested-tag"
                )
            else:
                _detail(state, value, request, content, event)
        rules.put(state, selection)
        if _ready_to_close(state, value):
            _complete(state, value, event)
    elif kind == "bonded_promise":
        if options != ("promise",) or answer.denied or action is None:
            raise WorkflowError("Author your actual promise to protect her")
        rules.put(state, selection)
        game.request(c, action, value.controllers[value.pair.token], "bonded_high", {})
    elif kind == "bonded_high":
        assert value.target is not None
        tags = {x.id: x for x in state.sheets[value.target.entity].tags}
        if (
            options
            or len(set(answer.denied)) != len(answer.denied)
            or any(x not in tags for x in answer.denied)
        ):
            raise WorkflowError(
                "The actual Pair chooses any of her own actual Tags, including none"
            )
        for index, tag in enumerate(answer.denied):
            _give(
                game,
                c,
                state,
                value,
                value.target,
                value.actor,
                tags[tag].label,
                event,
                "high-tag:" + str(index),
            )
        rules.put(state, selection)
        from girlframe.services.m3_bonded_support import place_above

        place_above(state, value.actor, value.pair)
        _complete(state, value, event)
    elif kind == "bonded_low":
        if len(options) != 1:
            raise WorkflowError("The actual intimate counterpart owns continuing or stopping")
        assert value.target is not None
        if options == ("continue",):
            other = state.sheets[value.target.entity]
            selected = [
                x
                for x in other.identities
                if x.id in answer.denied and x.marked and x.id not in other.sedation_locked
            ]
            if len(answer.denied) != 1 or len(selected) != 1:
                raise WorkflowError("Unmark one of your actual available marked Identities")
            selected[0].marked = False
            shift_status(state, int(value.actor.entity), 1)
        elif answer.denied:
            raise WorkflowError("Stopping weakens the real Bond; it does not unmark an Identity")
        else:
            _copy(state, change(state, value.actor, value.target, -1, event))
        rules.put(state, selection)
        _complete(state, value, event)
    elif kind == "bonded_intimacy":
        if len(options) != 1 or value.observer is None:
            raise WorkflowError("Choose the actual witnessed-affection outcome")
        if options == ("pair_tag",):
            _give(
                game,
                c,
                state,
                value,
                value.actor,
                value.pair,
                fields.get("tag", fields["account"]),
                event,
                "affection-pair-tag",
            )
        elif options == ("observer_tag",):
            from girlframe.engine.m2 import higher

            if not (
                higher(state, int(value.actor.entity), int(value.observer.entity))
                or higher(state, int(value.pair.entity), int(value.observer.entity))
            ):
                raise WorkflowError("Only an actual lower-Status onlooker can receive this Tag")
            _give(
                game,
                c,
                state,
                value,
                value.actor,
                value.observer,
                fields.get("tag", fields["account"]),
                event,
                "affection-observer-tag",
            )
        elif options == ("child",):
            play = fields.get("play", "")
            if play not in ("flirt", "brutalize", "snoop") or not fields.get("context", "").strip():
                raise WorkflowError(
                    "Describe one actual legal triggered Play against this onlooker"
                )
            rules.put(
                state,
                rules.Child(
                    id=value.id + ":child",
                    source=value.id,
                    actor=value.actor,
                    target=value.observer,
                    parent=None,
                    play=play,
                    account=fields["context"],
                    event=event,
                ),
            )
            rules.put(state, value.model_copy(update=dict(phase="child")))
        rules.put(state, selection)
        if options != ("child",):
            _complete(state, value, event)
    else:
        raise WorkflowError("Use the actual source-owned Bonded choice")


def _ready_to_close(state: GameState, value: rules.Source) -> bool:
    asked = next(
        (
            x
            for x in rules.records(state, rules.Selection)
            if x.source == value.id and x.kind == "bonded_mid"
        ),
        None,
    )
    answered = {
        x.request
        for x in rules.records(state, rules.Selection)
        if x.source == value.id and x.kind == "bonded_reply"
    }
    return bool(
        asked is not None and set(asked.options) <= answered and not _unbound_orders(state, value)
    )


def _unbound_orders(state: GameState, value: rules.Source) -> tuple[rules.Detail, ...]:
    return tuple(
        x
        for x in rules.records(state, rules.Detail)
        if x.source == value.id
        and x.kind == "order"
        and not any(y.detail == x.id for y in rules.records(state, rules.OrderBinding))
    )


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: Any,
    answer: ChoiceAnswer,
) -> bool:
    if row["kind"] not in KINDS:
        return False
    value = prove(game, c, state, action["data"]["bonded"]["source"])
    person = _choice_person(value, row["kind"])
    if str(row["actor_id"]) != str(value.controllers[person.token]):
        raise WorkflowError("Only the original actual chooser owns this response")
    _select(
        game,
        c,
        state,
        value,
        row["kind"],
        answer,
        action["data"]["response_event"],
        row["id"],
        action,
        json.loads(row["body_json"]).get("request"),
    )
    action["data"].setdefault("result", {}).update(
        source=value.id, phase=rules.get(state, value.id).phase
    )
    return True


def projection_options(state: GameState, value: rules.Source, kind: str) -> dict[str, str]:
    if kind == "bonded_side":
        return (
            dict(arrive="Be there now, close enough to touch", weapon="I needed and found a weapon")
            if value.tier == "high"
            else dict(
                stay="Stay, fidget and ask when she comes",
                arrive="Be there now, close enough to touch",
            )
        )
    if kind == "bonded_promise":
        return dict(promise="Take hold of her and promise to protect her")
    if kind == "bonded_mid":
        return dict(
            tag="Ask her to give me a Tag",
            secret="Ask her to tell me a secret",
            order="Ask her to give me an Order",
            appearance="Ask her to change my appearance",
        )
    if kind == "bonded_reply":
        return dict(give="Author my actual reply/performed shaping", decline="Decline the request")
    if kind == "bonded_low":
        return {
            "continue": "Keep going, lower her Status and unmark my Identity",
            "stop": "Stop and weaken our actual Bond",
        }
    if kind == "bonded_intimacy":
        return dict(
            draw_back="Draw back at the last moment",
            pair_tag="Give my Pair a Tag",
            child="Make an actual Play against the onlooker",
            observer_tag="Give an actual lower-Status onlooker a Tag",
        )
    return {}


def projection(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any], row: Any
) -> dict[str, Any]:
    value = prove(
        game, c, load_state(c, game.store.campaign_id), action["data"]["bonded"]["source"]
    )
    state = load_state(c, game.store.campaign_id)
    if viewer.user_id != int(row["actor_id"]):
        raise WorkflowError("Only the original chooser sees this private resource selector")
    person = _choice_person(value, row["kind"])
    sheet = state.sheets[person.entity]
    return dict(
        source=value.id,
        kind=row["kind"],
        tier=value.tier,
        options=list(projection_options(state, value, row["kind"]).items()),
        request=json.loads(row["body_json"]).get("request"),
        identities=[
            dict(id=x.id, label=x.name)
            for x in sheet.identities
            if x.marked and x.id not in sheet.sedation_locked
        ],
        tags=[dict(id=x.id, label=x.label) for x in sheet.tags]
        if row["kind"] == "bonded_high"
        else [],
        maximum=4
        if row["kind"] == "bonded_mid"
        else 2
        if row["kind"] == "bonded_side" and value.tier == "high"
        else 1,
    )


def _child(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Child:
    value = next((x for x in rules.records(state, rules.Child) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual witnessed-affection child source")
    source = prove(game, c, state, value.source)
    born = next(
        (x for x in rules.records(_history(c, game, value.event), rules.Child) if x.id == identity),
        None,
    )
    if (
        born is None
        or any(
            getattr(born, k) != getattr(value, k)
            for k in ("id", "source", "actor", "target", "parent", "play", "account", "event")
        )
        or source.kind != "intimacy"
        or value.actor != source.actor
        or value.target != source.observer
    ):
        raise WorkflowError("Preserve the actual child actor, onlooker and observed affection")
    if value.child:
        action = game.action(c, value.child)
        meta = action["data"].get("bonded_child", {})
        bound = next(
            (
                x
                for x in rules.records(_history(c, game, value.bound_event or ""), rules.Child)
                if x.id == identity
            ),
            None,
        )
        if (
            bound is None
            or bound.child != value.child
            or action["data"]["play"] != value.play
            or meta.get("child") != identity
            or action["data"].get("character_ids", {}).get(value.actor.entity)
            != value.actor.incarnation
        ):
            raise WorkflowError("Recover the real source-bound child Play")
    return value


def child_source(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not any(x.id == prepared.source_work for x in rules.records(state, rules.Child)):
        return None
    _access(game, c, viewer, rules.INTIMACY)
    value = _child(game, c, state, prepared.source_work or "")
    source = prove(game, c, state, value.source)
    if (
        source.phase != "child"
        or value.child
        or value.completed_event
        or value.actor != current_ref(state, viewer.user_id)
        or prepared.play != value.play
        or channel != source.cast.channel
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
        or not prepared.trigger_confirmed
        or prepared.context != value.account
        or prepared.target_actor not in (None, value.target)
        or prepared.target not in (None, int(value.target.entity))
    ):
        raise WorkflowError("Use the actual original triggered Play against this onlooker")
    _contact(game, c, state, source)
    return dict(
        child=value.id,
        source=source.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.target.model_dump(mode="json"),
        cast=source.cast.model_dump(mode="json"),
        table=sorted(
            set(source.controllers.values())
            | ({source.cast.facilitator} if source.cast.facilitator else set())
        ),
    )


def bind_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"]["bonded_child"]
    value = _child(game, c, state, meta["child"])
    if (
        value.child
        or action["actor_id"] != value.actor.entity
        or action["data"]["play"] != value.play
    ):
        raise WorkflowError("Bind the genuine actual child once")
    rules.put(state, value.model_copy(update=dict(child=action["id"], bound_event=event)))


def complete_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    value = _child(game, c, state, action["data"]["bonded_child"]["child"])
    if value.child != action["id"] or action["state"] != "complete":
        raise WorkflowError("Resolve the real child effects before closing witnessed affection")
    if value.completed_event:
        return
    _, total = _roll_source(game, c, action)
    source = rules.get(state, value.source)
    if total >= 8:
        rules.put(
            state,
            rules.Silence(
                id=value.id + ":silence",
                source=source.id,
                child=value.id,
                actor=source.actor,
                pair=source.pair,
                observer=value.target,
                observation=source.id,
                event=event,
            ),
        )
    rules.put(state, value.model_copy(update=dict(completed_event=event, total=total)))
    _complete(state, source, event)


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    if action["data"].get("bonded_child") and action["state"] == "complete":
        state = load_state(c, game.store.campaign_id)
        value = _child(game, c, state, action["data"]["bonded_child"]["child"])
        if value.completed_event:
            return
        receipt_event = str(uuid4())
        complete_child(game, c, state, action, receipt_event)
        game.event(
            c,
            int(action["actor_id"]),
            "bonded-child:" + value.id,
            "m3.bonded_child_completed",
            state,
            event_id=receipt_event,
            action_id=action["id"],
            source=value.source,
            completion_event=event,
        )


def order_authority(
    game: GameService, c: Connection, state: GameState, issuer: int, target: int, instruction: str
) -> dict[str, Any] | None:
    actor, recipient = current_ref(state, issuer), current_ref(state, target)
    for detail in rules.records(state, rules.Detail):
        if (
            detail.kind != "order"
            or detail.actor != actor
            or detail.target != recipient
            or detail.account != instruction
            or any(x.detail == detail.id for x in rules.records(state, rules.OrderBinding))
        ):
            continue
        source = prove(game, c, state, detail.source)
        if source.phase != "results":
            raise WorkflowError("Use the original still-pending real Pair Sex Order")
        return dict(
            detail=detail.id,
            source=detail.source,
            actor=actor.model_dump(mode="json"),
            target=recipient.model_dump(mode="json"),
            instruction=instruction,
            source_event=detail.event,
        )
    return None


def bind_order(
    game: GameService,
    c: Connection,
    state: GameState,
    authority: dict[str, Any],
    order_id: str,
    event: str,
) -> None:
    detail = next(
        (x for x in rules.records(state, rules.Detail) if x.id == authority.get("detail")), None
    )
    if detail is None or authority != order_authority(
        game, c, state, int(detail.actor.entity), int(detail.target.entity), detail.account
    ):
        raise WorkflowError("Preserve the exact pending instruction and actual Pair source")
    rules.put(
        state,
        rules.OrderBinding(
            id=detail.id + ":issued",
            detail=detail.id,
            source=detail.source,
            actor=detail.actor,
            target=detail.target,
            order=order_id,
            event=event,
        ),
    )
    source = rules.get(state, detail.source)
    if _ready_to_close(state, source):
        _complete(state, source, event)


def valid_order(game: GameService, c: Connection, state: GameState, body: dict[str, Any]) -> bool:
    authority = body.get("bonded")
    if not isinstance(authority, dict):
        return False
    detail = next(
        (x for x in rules.records(state, rules.Detail) if x.id == authority.get("detail")), None
    )
    if detail is None:
        return False
    prove(game, c, state, detail.source)
    binding = next(
        (
            x
            for x in rules.records(state, rules.OrderBinding)
            if x.detail == detail.id and x.order == body.get("id")
        ),
        None,
    )
    if binding is None:
        return False
    born = next(
        (
            x
            for x in rules.records(_history(c, game, binding.event), rules.OrderBinding)
            if x.id == binding.id
        ),
        None,
    )
    return bool(
        born == binding
        and authority
        == dict(
            detail=detail.id,
            source=detail.source,
            actor=detail.actor.model_dump(mode="json"),
            target=detail.target.model_dump(mode="json"),
            instruction=detail.account,
            source_event=detail.event,
        )
        and body.get("text") == detail.account
    )


def sex_route(
    game: GameService, c: Connection, state: GameState, prepared: PlayInput, channel: int
) -> dict[str, Any] | None:
    value = next(
        (
            x
            for x in rules.records(state, rules.Source)
            if x.id == prepared.source_work and x.route == "delegated"
        ),
        None,
    )
    if value is None:
        return None
    value = prove(game, c, state, value.id)
    if (
        value.actor != current_ref(state, int(value.actor.entity))
        or value.phase != "accepted"
        or channel != value.cast.channel
        or not value.delegated_rule
    ):
        raise WorkflowError("Use the actual original Pair's source-authenticated Sex rule")
    _contact(game, c, state, value)
    return dict(
        source=value.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.target.model_dump(mode="json") if value.target else None,
        pair=value.pair.model_dump(mode="json"),
        rule=value.delegated_rule,
        cast=value.cast.model_dump(mode="json"),
        source_event=value.event,
    )


def prove_route(game: GameService, c: Connection, state: GameState, route: dict[str, Any]) -> None:
    value = prove(game, c, state, str(route.get("source", "")))
    if route != dict(
        source=value.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.target.model_dump(mode="json") if value.target else None,
        pair=value.pair.model_dump(mode="json"),
        rule=value.delegated_rule,
        cast=value.cast.model_dump(mode="json"),
        source_event=value.event,
    ):
        raise WorkflowError("Preserve the actual borrowed rule and original participants")
    if value.route != "delegated" or not value.delegated_rule:
        raise WorkflowError("Only the actual original Pair's current Sex rule may be delegated")
    if not has_rule(
        state.sheets[value.pair.entity], value.delegated_rule, rule_book(value.delegated_rule)
    ):
        raise WorkflowError("Recover the actual current source rule, not an old book name")


class BondedService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        body: dict[str, Any],
        operation: Any,
        rule: str = rules.PAIR,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            _access(self.game, c, viewer, rule)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, body, operation, auto_audit=False, authorize=access
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        kind: str,
        account: str,
        *,
        target: ActorRef | None = None,
        observer: ActorRef | None = None,
        route: str = "pair",
        apart: bool = False,
        delegated_rule: str | None = None,
    ) -> dict[str, Any]:
        rule = dict(side=rules.SIDE, intimacy=rules.INTIMACY, sex=rules.SEX).get(kind)
        if rule is None:
            raise WorkflowError("Choose a genuine printed Bonded source")

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            actual_pair, lineage = original_pair(self.game, c, state, actor, rule)
            if (
                state.revision != revision
                or self.game.pending_actions(c)
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Use the actual current idle source and your own factual account"
                )
            cast = _cast(self.game, c, state, channel)
            if not any(x.id == cast.id for x in state.scene_casts):
                state.scene_casts.append(cast)
            if kind == "sex":
                target_ref = target or actual_pair
                if target_ref == actor or (target_ref == actual_pair) != (route == "pair"):
                    raise WorkflowError("Use actual Pair Sex or an explicit non-Pair route")
            else:
                target_ref = None
                if target is not None or route != "pair":
                    raise WorkflowError("This source is not a substituted Sex route")
            if (
                kind == "intimacy"
                and (observer is None or observer in (actor, actual_pair))
                or kind != "intimacy"
                and observer is not None
            ):
                raise WorkflowError("Use a distinct actual witnessed-affection onlooker")
            refs = (actor, target_ref) if kind == "sex" else (actor, actual_pair, observer)
            people = [_native(self.game, c, state, x) for x in refs if x is not None]
            event, identity = str(uuid4()), str(uuid4())
            assert self.store.policy.m3_approval is not None
            delegated = None
            if route == "delegated":
                candidates = current_pair_sex_rules(state, actual_pair)
                if delegated_rule is not None:
                    if delegated_rule not in candidates:
                        raise WorkflowError(
                            "Choose only the actual original Pair's current owned Sex rule"
                        )
                    delegated = delegated_rule
                elif len(candidates) == 1:
                    delegated = candidates[0]
                else:
                    raise WorkflowError("Select the actual current Pair Sex source explicitly")
                if delegated == rules.SEX:
                    raise WorkflowError(
                        "SOURCE_SEX_ROUTING_CYCLE: use the explicit unrolled7 alternative"
                    )
                gate = Access(self.store)
                assert gate.registry is not None
                gate.registry.require_available(delegated)
            value = rules.Source.model_validate(
                dict(
                    id=identity,
                    kind=kind,
                    actor=actor,
                    pair=actual_pair,
                    target=target_ref,
                    observer=observer,
                    controllers={x.ref.token: x.controller for x in people},
                    vessels={x.ref.token: x.vessel_id for x in people},
                    cast=cast,
                    registry=self.store.policy.m3_approval.registry_sha256,
                    pair_source=lineage,
                    apart=apart,
                    event=event,
                    account=account.strip(),
                    phase="invited" if kind == "sex" else "accepted",
                    route=route,
                    delegated_rule=delegated,
                )
            )
            _contact(self.game, c, state, value)
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_proposed",
                state,
                event_id=event,
                source=identity,
                source_kind=kind,
            )
            return dict(id=identity, revision=state.revision, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.bonded_proposed",
            dict(
                channel=channel,
                revision=revision,
                kind=kind,
                account=account,
                target=target.model_dump(mode="json") if target else None,
                observer=observer.model_dump(mode="json") if observer else None,
                route=route,
                apart=apart,
                delegated_rule=delegated_rule,
            ),
            operation,
            rule,
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            person = current_ref(state, viewer.user_id)
            if (
                state.revision != revision
                or value.phase != "invited"
                or person != value.target
                or value.controllers.get(person.token) != viewer.user_id
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the actual original intimate counterpart confirms their own choice"
                )
            _contact(self.game, c, state, value)
            event = str(uuid4())
            rules.put(
                state,
                rules.Consent(
                    id=identity + ":consent",
                    source=identity,
                    person=person,
                    controller=viewer.user_id,
                    accepted=accept,
                    event=event,
                    account=account.strip(),
                ),
            )
            rules.put(
                state, value.model_copy(update=dict(phase="accepted" if accept else "declined"))
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_confirmed",
                state,
                event_id=event,
                source=identity,
                accepted=accept,
            )
            return dict(
                id=identity, revision=state.revision, phase="accepted" if accept else "declined"
            )

        return self._write(
            viewer,
            key,
            "m3.bonded_confirmed",
            dict(id=identity, revision=revision, accept=accept, account=account),
            operation,
            rules.SEX,
        )

    def activate(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            _access(self.game, c, viewer, rules.INTIMACY if value.kind == "intimacy" else rules.SEX)
            if (
                state.revision != revision
                or value.actor != current_ref(state, viewer.user_id)
                or value.phase != "accepted"
                or self.game.pending_actions(c)
                or (value.kind != "intimacy" and value.route != "seven")
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Record the actual performed affection or confirmed unrolled7 source"
                )
            _contact(self.game, c, state, value)
            event = str(uuid4())
            rules.put(
                state,
                rules.Activation(
                    id=identity + ":activation",
                    source=identity,
                    actor=value.actor,
                    event=event,
                    account=account.strip(),
                ),
            )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        phase="results",
                        effect_event=event,
                        tier="low" if value.route == "seven" else None,
                    )
                ),
            )
            if value.route == "seven":
                from girlframe.services.p1_unrolled_sex import offer

                offer(self.game, c, state, rules.get(state, identity), event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_activated",
                state,
                event_id=event,
                source=identity,
            )
            return dict(id=identity, revision=state.revision, no_roll=True)

        return self._write(
            viewer,
            key,
            "m3.bonded_activated",
            dict(id=identity, revision=revision, account=account),
            operation,
            rules.PAIR,
        )

    def choose(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, answer: ChoiceAnswer
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            _access(self.game, c, viewer, rules.INTIMACY if value.kind == "intimacy" else rules.SEX)
            kind = "bonded_intimacy" if value.kind == "intimacy" else "bonded_low"
            person = _choice_person(value, kind)
            if (
                state.revision != revision
                or person != current_ref(state, viewer.user_id)
                or value.action is not None
                or value.kind != "intimacy"
                and value.route != "seven"
            ):
                raise WorkflowError("Only the actual unrolled source chooser owns this decision")
            from girlframe.services.p1_source_pause import require_ready

            require_ready(self.game, c, state, identity)
            if value.route == "seven":
                from girlframe.services.p1_unrolled_sex import require_complete

                require_complete(self.game, c, state, identity)
            event = str(uuid4())
            _select(self.game, c, state, value, kind, answer, event, str(uuid4()), None)
            self.game.event(
                c, viewer.user_id, key, "m3.bonded_selected", state, event_id=event, source=identity
            )
            return dict(
                id=identity, revision=state.revision, phase=rules.get(state, identity).phase
            )

        return self._write(
            viewer,
            key,
            "m3.bonded_selected",
            dict(id=identity, revision=revision, answer=answer.model_dump(mode="json")),
            operation,
        )

    def help(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if (
                state.revision != revision
                or value.kind != "side"
                or value.tier != "low"
                or current_ref(state, viewer.user_id) != value.pair
                or not account.strip()
                or len(account) > 1200
                or any(x.source == identity for x in rules.records(state, rules.PairHelp))
            ):
                raise WorkflowError(
                    "Only the actual original Pair records their genuine performed help"
                )
            people = [_native(self.game, c, state, x) for x in (value.actor, value.pair)]
            if (
                any(x.cell is None or x.vessel_id is None for x in people)
                or people[0].cell != people[1].cell
            ):
                raise WorkflowError(
                    "Record actual co-present physical help, never remote fictional aid"
                )
            event = str(uuid4())
            rules.put(
                state,
                rules.PairHelp(
                    id=identity + ":help",
                    source=identity,
                    actor=value.actor,
                    pair=value.pair,
                    controller=viewer.user_id,
                    event=event,
                    account=account.strip(),
                ),
            )
            self.game.event(
                c, viewer.user_id, key, "m3.bonded_helped", state, event_id=event, source=identity
            )
            return dict(id=identity, revision=state.revision, helped=True)

        return self._write(
            viewer,
            key,
            "m3.bonded_helped",
            dict(id=identity, revision=revision, account=account),
            operation,
            rules.SIDE,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for source in rules.records(state, rules.Source):
            if viewer.user_id not in source.controllers.values():
                continue
            value = prove(self.game, c, state, source.id)
            chooser: int | None = None
            if value.phase == "invited" and value.target is not None:
                chooser = value.controllers[value.target.token]
            elif value.phase == "accepted" or value.phase == "child":
                chooser = value.controllers[value.actor.token]
            elif value.phase == "results":
                orders = _unbound_orders(state, value)
                if orders:
                    chooser = orders[0].controller
                elif value.action:
                    pending = self.game.pending(c, value.action)
                    chooser = next(
                        (
                            int(x["actor_id"])
                            for x in pending
                            if int(x["actor_id"]) == viewer.user_id
                        ),
                        None,
                    )
                elif value.kind == "intimacy":
                    chooser = value.controllers[value.actor.token]
                elif value.target is not None:
                    chooser = value.controllers[value.target.token]
            result.append(
                dict(
                    id=value.id,
                    revision=state.revision,
                    label={
                        "side": "Always By Her Side",
                        "intimacy": "Witnessed affection",
                        "sex": "Bonded intimacy",
                    }[value.kind]
                    + " · "
                    + value.phase,
                    phase="pending" if value.phase not in ("complete", "declined") else "complete",
                    pending=chooser == viewer.user_id,
                    source_phase=value.phase,
                )
            )
        return result

    def menu(self, viewer: GuildViewer, channel: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            history = self._tasks(c, viewer)
            actor = (
                current_ref(state, viewer.user_id) if str(viewer.user_id) in state.sheets else None
            )
            data: dict[str, Any] = dict(
                revision=state.revision,
                history=history,
                pair=None,
                people=[],
                actor=None,
                available=[],
            )
            if actor is None:
                return data
            sheet = state.sheets[actor.entity]
            if not any(has_rule(sheet, rule, "BONDED") for rule in rules.RULES):
                return data
            _access(self.game, c, viewer, rules.PAIR)
            actual, _ = original_pair(self.game, c, state, actor)
            data.update(
                actor=actor.model_dump(mode="json"),
                pair=actual.model_dump(mode="json"),
                pair_label=state.sheets[actual.entity].callsign,
                delegated_rules=[
                    dict(id=x, label=rule_book(x) + " Sex Play")
                    for x in current_pair_sex_rules(state, actual)
                ],
                available=[
                    x
                    for x in ("side", "intimacy", "sex")
                    if has_rule(
                        sheet,
                        dict(side=rules.SIDE, intimacy=rules.INTIMACY, sex=rules.SEX)[x],
                        "BONDED",
                    )
                ],
            )
            if channel is not None:
                cast = _cast(self.game, c, state, channel)
                for role in cast.roles:
                    if role.actor.kind != "pilot" or role.actor == actor:
                        continue
                    try:
                        person = _native(self.game, c, state, role.actor)
                    except (ValueError, WorkflowError):
                        continue
                    data["people"].append(
                        dict(ref=role.actor.model_dump(mode="json"), label=person.label)
                    )
            return data

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if viewer.user_id not in value.controllers.values():
                raise WorkflowError(
                    "Only the original actual participants read this private source"
                )
            person = next(x for x in _people(value) if value.controllers[x.token] == viewer.user_id)
            selected = [x for x in rules.records(state, rules.Selection) if x.source == identity]
            details = [
                x
                for x in rules.records(state, rules.Detail)
                if x.source == identity and person in (x.actor, x.target)
            ]
            child = next(
                (x for x in rules.records(state, rules.Child) if x.source == identity), None
            )
            orders = [x for x in _unbound_orders(state, value) if x.controller == viewer.user_id]
            low_person = value.target if value.kind == "sex" else value.actor
            own = state.sheets[person.entity]
            from girlframe.services.p1_source_pause import projection as pause_projection

            pause = (
                pause_projection(self.game, c, identity)
                if value.action is None and value.effect_event
                else None
            )
            from girlframe.services.p1_unrolled_sex import tasks as gender_tasks

            gender = (
                gender_tasks(self.game, c, state, value, viewer) if value.route == "seven" else []
            )
            return dict(
                unrolled_gender=gender,
                pause=pause,
                id=identity,
                revision=state.revision,
                kind=value.kind,
                phase=value.phase,
                route=value.route,
                delegated_rule=value.delegated_rule,
                account=value.account,
                actor=value.actor.model_dump(mode="json"),
                pair=value.pair.model_dump(mode="json"),
                target=value.target.model_dump(mode="json") if value.target else None,
                channel=value.cast.channel,
                action=value.action,
                can_confirm=value.phase == "invited" and person == value.target,
                can_roll=value.phase == "accepted"
                and person == value.actor
                and value.route == "pair"
                and value.kind != "intimacy",
                can_activate=value.phase == "accepted"
                and person == value.actor
                and (value.route == "seven" or value.kind == "intimacy"),
                can_choose=value.phase == "results"
                and value.action is None
                and person == (value.actor if value.kind == "intimacy" else low_person),
                can_help=value.kind == "side"
                and value.tier == "low"
                and person == value.pair
                and not any(x.source == identity for x in rules.records(state, rules.PairHelp)),
                options=list(
                    projection_options(
                        state,
                        value,
                        "bonded_intimacy" if value.kind == "intimacy" else "bonded_low",
                    ).items()
                ),
                identities=[
                    dict(id=x.id, label=x.name)
                    for x in own.identities
                    if x.marked and x.id not in own.sedation_locked
                ],
                selections=[
                    dict(
                        kind=x.kind,
                        request=x.request,
                        options=x.options,
                        text=(
                            x.text
                            if x.person == person
                            or (value.kind == "sex" and person in (value.actor, value.target))
                            else json.dumps(
                                {
                                    k: v
                                    for k, v in _text(x.text).items()
                                    if k in ("account", "question")
                                }
                            )
                            if value.kind == "side" and person == value.pair
                            else ""
                        ),
                        identities=x.identities if x.person == person else (),
                    )
                    for x in selected
                ],
                details=[x.model_dump(mode="json") for x in details],
                orders=[x.model_dump(mode="json") for x in orders],
                delegation=next(
                    (
                        x.model_dump(mode="json")
                        for x in rules.records(state, rules.Delegation)
                        if x.source == identity
                    ),
                    None,
                ),
                child=child.model_dump(mode="json") if child and person == value.actor else None,
                silent=bool(
                    value.observer and not rules.can_disclose(state, value.observer, value.id)
                ),
            )


def unrolled_parties(state: GameState, source_id: str) -> tuple[ActorRef, ...]:
    value = rules.get(state, source_id)
    if (
        value.kind != "sex"
        or value.route != "seven"
        or value.target is None
        or not value.effect_event
    ):
        return ()
    return value.actor, value.target


def admit_delegation(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    rule: str,
    bonded_source: str | None,
) -> bool:
    """Only a particular proved borrowed rule; never a global rule entitlement."""
    if bonded_source is None:
        return False
    value = prove(game, c, state, bonded_source)
    if (
        value.route != "delegated"
        or value.actor != actor
        or value.target != target
        or value.delegated_rule != rule
        or value.phase not in ("accepted", "bound", "complete")
    ):
        raise WorkflowError("Use the exact original Pair's delegated Sex source and participants")
    origin = _history(c, game, value.event)
    actual_pair, _ = original_pair(game, c, origin, actor, rules.SEX)
    if actual_pair != value.pair or not has_rule(
        origin.sheets[actual_pair.entity], rule, rule_book(rule)
    ):
        raise WorkflowError("Preserve the actual source-time Pair's owned Sex rule")
    if value.phase != "complete":
        current_pair, _ = original_pair(game, c, state, actor, rules.SEX)
        if current_pair != actual_pair or not has_rule(
            state.sheets[current_pair.entity], rule, rule_book(rule)
        ):
            raise WorkflowError("The actual original Pair must still hold this source Sex rule")
    if not any(x.source == value.id and x.accepted for x in rules.records(state, rules.Consent)):
        raise WorkflowError("Preserve the actual other participant's voluntary confirmation")
    return True


def bind_delegation(
    game: GameService,
    c: Connection,
    state: GameState,
    bonded_source: str,
    session: str,
    rule: str,
    event: str,
) -> None:
    value = prove(game, c, state, bonded_source)
    if (
        value.phase != "accepted"
        or value.target is None
        or any(x.source == value.id for x in rules.records(state, rules.Delegation))
    ):
        raise WorkflowError("Bind only one genuine counterpart source to the original delegation")
    admit_delegation(game, c, state, value.actor, value.target, rule, bonded_source)
    rules.put(
        state,
        rules.Delegation(
            id=value.id + ":delegation",
            source=value.id,
            session=session,
            rule=rule,
            actor=value.actor,
            target=value.target,
            event=event,
        ),
    )
    rules.put(state, value.model_copy(update=dict(phase="bound")))


def prove_delegation(
    game: GameService,
    c: Connection,
    state: GameState,
    bonded_source: str | None,
    session: str,
    actor: ActorRef,
    target: ActorRef,
    rule: str,
) -> None:
    if bonded_source is None:
        return
    admit_delegation(game, c, state, actor, target, rule, bonded_source)
    link = next(
        (x for x in rules.records(state, rules.Delegation) if x.source == bonded_source), None
    )
    if link is None or (link.session, link.actor, link.target, link.rule) != (
        session,
        actor,
        target,
        rule,
    ):
        raise WorkflowError("Preserve the exact original delegated consumer and participants")
    birth = next(
        (
            x
            for x in rules.records(_history(c, game, link.event), rules.Delegation)
            if x.id == link.id
        ),
        None,
    )
    if birth is None or any(
        getattr(birth, k) != getattr(link, k)
        for k in ("id", "source", "session", "rule", "actor", "target", "event")
    ):
        raise WorkflowError("Recover the immutable genuine delegated source birth")


def synchronize_delegation(
    game: GameService, c: Connection, action: dict[str, Any], event: str
) -> None:
    """Root calls after the real delegated consumer and its own completion checks."""
    state = load_state(c, game.store.campaign_id)
    link = next(
        (
            x
            for x in rules.records(state, rules.Delegation)
            if x.session in (action["id"], action["data"].get("prepared", {}).get("source_work"))
        ),
        None,
    )
    if link is None or link.completed_event or action["state"] != "complete":
        return
    source = prove(game, c, state, link.source)
    prove_delegation(game, c, state, link.source, link.session, link.actor, link.target, link.rule)
    _roll_source(game, c, action)
    final = str(uuid4())
    rules.put(state, link.model_copy(update=dict(action=action["id"], completed_event=final)))
    _complete(state, source, final)
    game.event(
        c,
        int(link.actor.entity),
        "bonded-delegation:" + link.id,
        "m3.bonded_delegation_completed",
        state,
        event_id=final,
        action_id=action["id"],
        source=source.id,
        completion_event=event,
    )


def pre_roll_child(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    _access(game, c, viewer, rules.INTIMACY)
    value = _child(game, c, state, action["data"]["bonded_child"]["child"])
    source = prove(game, c, state, value.source)
    if (
        value.child != action["id"]
        or value.completed_event
        or source.phase != "child"
        or value.actor != current_ref(state, viewer.user_id)
        or action["actor_id"] != value.actor.entity
        or action["data"].get("prepared", {}).get("source_work") != value.id
    ):
        raise WorkflowError("Roll only the original bound onlooker child once")
    _contact(game, c, state, source)


def intercept_finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    meta = action["data"].get("bonded")
    if not isinstance(meta, dict):
        return False
    value = rules.get(state, meta["source"])
    if value.phase != "complete":
        action["state"] = "awaiting_choices"
        return True
    return False


def delegation_for_play(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, prepared: PlayInput
) -> dict[str, Any] | None:
    link = next(
        (x for x in rules.records(state, rules.Delegation) if x.session == prepared.source_work),
        None,
    )
    if link is None:
        return None
    plays = {
        "girl.alpha.sex-play": "alpha_sex",
        "girl.princess.sex-play": "princess_sex",
        "girl.mockingbird.sex-play": "mockingbird_sex",
        "girl.stim-blissed.sex-play": "stim_sex",
        "girl.oldgen.sex-play": "oldgen_sex",
        "girl.casualty.sex-play": "casualty_sex",
        "girl.vatgrown.sex-play": "vatgrown_sex",
        "girl.newgirl.sex-play": "newgirl_sex",
    }
    if actor != link.actor or plays.get(link.rule) != prepared.play or link.completed_event:
        raise WorkflowError("Admit only the actual original actor's fixed delegated Sex Play")
    prove_delegation(game, c, state, link.source, link.session, link.actor, link.target, link.rule)
    return dict(
        source=link.source,
        session=link.session,
        rule=link.rule,
        actor=link.actor.model_dump(mode="json"),
        target=link.target.model_dump(mode="json"),
    )


def rule_book(rule: str) -> str:
    books = {
        "girl.alpha.sex-play": "ALPHA",
        "girl.princess.sex-play": "PRINCESS",
        "girl.mockingbird.sex-play": "MOCKINGBIRD",
        "girl.stim-blissed.sex-play": "STIM-BLISSED",
        "girl.oldgen.sex-play": "OLDGEN",
        "girl.casualty.sex-play": "CASUALTY",
        "girl.vatgrown.sex-play": "VATGROWN",
        "girl.newgirl.sex-play": "NEWGIRL",
        "girl.am.sex-play": "AM",
        rules.SEX: "BONDED",
    }
    if rule not in books:
        raise WorkflowError("Recover the actual supported original Pair Sex rule")
    return books[rule]


def current_pair_sex_rules(state: GameState, actual_pair: ActorRef) -> tuple[str, ...]:
    sheet = state.sheets[actual_pair.entity]
    native = "girl." + sheet.girl.lower() + ".sex-play"
    runtime = sheet.girl_runtime
    candidates = {native}
    if runtime:
        candidates.update(
            x.acquired_rule for x in runtime.swaps if x.acquired_rule.endswith(".sex-play")
        )
        candidates.update(x for x in runtime.retained_rules if x.endswith(".sex-play"))
    return tuple(sorted(x for x in candidates if has_rule(sheet, x, rule_book(x))))


def require_disclosure(
    game: GameService, c: Connection, state: GameState, speaker: ActorRef, observation: str
) -> None:
    for silence in rules.records(state, rules.Silence):
        if silence.observer != speaker or silence.observation != observation:
            continue
        source = prove(game, c, state, silence.source)
        child = _child(game, c, state, silence.child)
        saved = next(
            (
                x
                for x in rules.records(_history(c, game, silence.event), rules.Silence)
                if x.id == silence.id
            ),
            None,
        )
        if (
            saved != silence
            or not child.completed_event
            or child.completed_event != silence.event
            or child.total is None
            or child.total < 8
            or child.target != speaker
            or source.id != observation
        ):
            raise WorkflowError("Recover the actual successful observed-affection child source")
        raise WorkflowError(
            "The successful source Play prevents this actual observer telling what they saw; "
            "OOC safety is unchanged"
        )
