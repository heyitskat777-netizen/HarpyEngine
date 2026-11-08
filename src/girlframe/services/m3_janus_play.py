"""Living Battery uses the real reviewed contact and the shared owned roll protocol."""

import json
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_janus_link as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_janus import BATTERY, bound, find, ref
from girlframe.engine.m3_janus_link_state import BatteryChoice, BatteryLink, BrainMessage
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.m3_frame_control import prepare_battery
from girlframe.services.m3_frame_control import prove as prove_contact
from girlframe.services.m3_janus import prove_core
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("janus_erase", "janus_select", "janus_answer", "janus_void_threshold")


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    access = Access(game.store)
    access.authorize(c, viewer, "plays", director_response=action is not None)
    assert access.registry is not None
    access.registry.require_available(
        "frame.janus.pandora"
        if action is not None and action["data"]["janus"].get("mode") == "pandora"
        else BATTERY
    )
    if action is not None:
        meta = action["data"]["janus"]
        approval = game.store.policy.m3_approval
        if approval is None or meta["registry"] != approval.registry_sha256:
            raise WorkflowError("Recover this original Living Battery source approval")
        state = load_state(c, game.store.campaign_id)
        if fingerprint(_cast(game, c, state, int(action["channel_id"]))) != meta["cast_sha256"]:
            raise WorkflowError("Recover the actual original neural-link scene cast")


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    *,
    channel: int,
) -> dict[str, Any]:
    if prepared.play == "pandora_birth":
        from girlframe.services.m3_janus_pandora import prepare as prepare_birth

        return prepare_birth(game, c, viewer, prepared, state, channel=channel)
    authorize(game, c, viewer)
    if prepared.play != "living_battery":
        raise WorkflowError("This JANUS Play has no implemented source result yet")
    actor = current_ref(state, viewer.user_id)
    target = prepared.target_actor
    own = resolve(state, actor, profiles(c, game.store.campaign_id))
    value = bound(state, actor, str(own.frame_instance))
    if state.sheets[actor.entity].frame not in ("JANUS", "JANUS-B"):
        raise WorkflowError("Recover actual Living Battery ownership on this non-JANUS Frame")
    from girlframe.engine.m3_janus_requisitions import UNIVERSAL
    from girlframe.services.m3_janus_requisitions import owned

    universal = owned(c, game, state, actor, UNIVERSAL)
    if target is None or own.frame_instance is None:
        raise WorkflowError("Choose an actual other battery and original Frame")
    if value is None or target != ref(value) or not value.alive:
        if universal is None:
            raise WorkflowError("Use the actual attached Core, or acquire Universal Plug")
    actual_target = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if not actual_target.alive or actual_target.controller is None:
        raise WorkflowError("Use an actual living other mind with its original controller")
    actual_core = find(state, target)
    if actual_core is not None:
        prove_core(c, game, state, target)
    if (
        prepared.heat
        or prepared.identity
        or prepared.gain
        or prepared.pair_share
        or prepared.target is not None
        or prepared.parent
        or prepared.off_duty_id
        or prepared.order_id
        or prepared.source_work
        or prepared.obeying_orders
        or prepared.order_account
        or not prepared.context.strip()
        or not prepared.trigger_confirmed
    ):
        raise WorkflowError("Living Battery rolls only actual battery Tags, without spending Heat")
    contact = prepare_battery(game, c, state, actor, target, channel)
    if any(x.connection == contact["connection"] for x in state.battery_links):
        raise WorkflowError("This original spinal contact already has its one Living Battery roll")
    cast = _cast(game, c, state, channel)
    if not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles):
        raise WorkflowError("Join this actual scene as the original JANUS Pilot")
    assert game.store.policy.m3_approval is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        actor_controller=viewer.user_id,
        target_controller=actual_target.controller,
        contact=contact,
        core_source=actual_core.source_event if actual_core else None,
        universal=universal.id if universal else None,
        tags=[x[0] for x in rules.battery_tags(state, target)],
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted({x.controller for x in cast.roles} | {cast.facilitator}),
        registry=game.store.policy.m3_approval.registry_sha256,
        phase="unrolled",
    )


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    if action["data"]["janus"].get("mode") == "pandora":
        from girlframe.services.m3_janus_pandora import pre_roll as pre_birth

        pre_birth(game, c, viewer, state, action)
        return
    meta = action["data"]["janus"]
    actor, target = ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(meta["target"])
    if meta.get("universal"):
        from girlframe.engine.m3_janus_requisitions import UNIVERSAL
        from girlframe.services.m3_janus_requisitions import owned

        grant = owned(c, game, state, actor, UNIVERSAL)
        if grant is None or grant.id != meta["universal"]:
            raise WorkflowError("Recover the actual Universal Plug entitlement before rolling")
    contact = prepare_battery(
        game,
        c,
        state,
        actor,
        target,
        int(action["channel_id"]),
        identity=meta["contact"]["connection"],
    )
    if (
        contact != meta["contact"]
        or [x[0] for x in rules.battery_tags(state, target)] != meta["tags"]
    ):
        raise WorkflowError("Recover the original actual contact and battery Tags before rolling")
    if any(x.connection == contact["connection"] for x in state.battery_links):
        raise WorkflowError("The original contact already has a known roll")
    event = str(uuid4())
    identity = str(uuid4())
    rules.put(
        state,
        BatteryLink(
            id=identity,
            caster=actor,
            caster_controller=meta["actor_controller"],
            caster_frame_owner=ActorRef.model_validate(contact["caster_frame_owner"]),
            caster_frame=contact["caster_frame"],
            battery=target,
            battery_controller=meta["target_controller"],
            core_source=meta["core_source"],
            connection=contact["connection"],
            source_action=action["id"],
            source_event=event,
            source_cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
            source_tags=tuple(meta["tags"]),
            universal=bool(meta.get("universal")),
        ),
    )
    meta.update(link=identity, roll_event=event)


def prove_link(game: GameService, c: Connection, state: GameState, identity: str) -> BatteryLink:
    value = rules.get(state, identity)
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover this actual original Living Battery raw-roll event")
    original = rules.get(GameState.model_validate_json(raw), identity)
    stable = (
        "id",
        "caster",
        "caster_controller",
        "caster_frame_owner",
        "caster_frame",
        "battery",
        "battery_controller",
        "core_source",
        "connection",
        "source_action",
        "source_event",
        "source_cast",
        "source_tags",
        "universal",
    )
    if any(getattr(original, key) != getattr(value, key) for key in stable):
        raise WorkflowError("Preserve the original battery, person, contact and raw-roll source")
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        .mappings()
        .first()
    )
    if (
        event is None
        or event["kind"] != "m3.rolled"
        or json.loads(event["payload_json"]).get("action_id") != value.source_action
    ):
        raise WorkflowError("This link needs its actual shared raw-roll receipt source")
    assert value.connection is not None
    prove_contact(game, c, state, value.connection)
    return value


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if action["data"]["janus"].get("mode") == "pandora":
        from girlframe.services.m3_janus_pandora import results as birth_results

        birth_results(game, c, state, action)
        return
    meta = action["data"]["janus"]
    value = prove_link(game, c, state, meta["link"])
    if value.tier is not None:
        raise WorkflowError("This actual known battery result already started")
    rules.put(state, value.model_copy(update={"tier": action["data"]["result"]["tier"]}))
    meta["phase"] = "choosing"
    game.request(
        c,
        action,
        value.caster_controller,
        "janus_erase" if action["data"]["result"]["tier"] == "low" else "janus_select",
    )


def projection(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    if action["data"]["janus"].get("mode") == "pandora":
        from girlframe.services.m3_janus_pandora import projection as birth_projection

        return birth_projection(game, c, state, action)
    value = prove_link(game, c, state, action["data"]["janus"]["link"])
    if request["kind"] == "janus_answer":
        return dict(question=value.question, private=True)
    own = state.sheets[value.caster.entity]
    return dict(
        count={"low": 1, "mid": 2, "high": 4}[str(value.tier)],
        options=[
            dict(id=x, label=y)
            for x, y in (
                ("heat", "Gain one to four Heat"),
                ("bond", "Deepen your actual Bond"),
                ("identities", "Unmark up to two actual Identities"),
                ("cognition", "Harpy Cognition until unplugged"),
                ("offset", "Offset Emotional Load until unplugged"),
                ("question", "Ask a private question and communicate via brain link"),
            )
        ],
        tags=[dict(id=x[0], label=x[1]) for x in rules.battery_tags(state, value.battery)],
        identities=[dict(id=x.id, label=x.name) for x in own.identities if x.marked],
        universal=value.universal and value.tier != "low",
    )


def _finish(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    if not game.pending(c, action["id"]):
        from girlframe.services.m3_janus_storage import intercept_replug

        if intercept_replug(game, c, state, action):
            return
        action["data"]["janus"]["phase"] = "complete"
        ChoiceEngine(game).finish(c, state, action)


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    if action["data"]["janus"].get("mode") == "pandora":
        from girlframe.services.m3_janus_pandora import apply as apply_birth

        apply_birth(game, c, state, action, request, answer)
        return
    value = prove_link(game, c, state, action["data"]["janus"]["link"])
    event = action["data"]["response_event"]
    kind = request["kind"]
    if answer.flag is not None or answer.member is not None or answer.denied:
        raise WorkflowError("Use only this actual printed battery choice's fields")
    if kind == "janus_erase":
        if (
            len(answer.options) != (1 if rules.battery_tags(state, value.battery) else 0)
            or answer.text
            or answer.fields
            or answer.number is not None
        ):
            raise WorkflowError("Erase one actual battery Tag, or record that no Tag exists")
        changed = rules.erase_low_tag(
            state, value.id, answer.options[0] if answer.options else None, event=event
        )
        if not rules.battery_tags(changed, value.battery) and answer.options:
            changed = rules.corrupt_frame(changed, value.id, event=event)
        _copy(state, changed)
        game.request(c, action, value.caster_controller, "janus_select")
    elif kind == "janus_select":
        if set(answer.fields) - {"identities", "tag"}:
            raise WorkflowError("Use only the real selected Identities field")
        identities = tuple(json.loads(answer.fields.get("identities", "[]")))
        changed = rules.choices(
            state,
            value.id,
            cast(tuple[BatteryChoice, ...], answer.options),
            event=event,
            heat=answer.number or 0,
            identities=identities,
            question=answer.text,
            target_tag=answer.fields.get("tag"),
            bindings=profiles(c, game.store.campaign_id),
        )
        _copy(state, changed)
        if "question" in answer.options:
            game.request(c, action, value.battery_controller, "janus_answer")
        else:
            _finish(game, c, state, action)
    elif kind == "janus_answer":
        if answer.options or answer.fields or answer.number is not None or not answer.text.strip():
            raise WorkflowError("The actual other mind's controller supplies the private response")
        if value.phase != "question" or value.answer_event is not None:
            raise WorkflowError("Only the original pending private question may be answered")
        rules.put(
            state,
            value.model_copy(
                update=dict(answer=answer.text.strip(), answer_event=event, phase="connected")
            ),
        )
        _finish(game, c, state, action)
    else:
        raise WorkflowError("Resolve the actual source-bound battery continuation")


def _history(game: GameService, c: Connection, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual Living Battery effect history")
    return GameState.model_validate_json(raw)


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    if action["data"]["janus"].get("mode") == "pandora":
        return
    from girlframe.services.m3_janus_storage import synchronize_replug

    synchronize_replug(game, c, action, event)
    from girlframe.services.m3_void import prepare_threshold
    from girlframe.services.m3_work import related

    meta = action["data"]["janus"]
    state = load_state(c, game.store.campaign_id)
    value = prove_link(game, c, state, meta["link"])
    if value.frame_takeover != event or meta.get("void_work"):
        return
    owner = value.caster_frame_owner
    sheet = state.sheets.get(owner.entity) if owner.kind == "pilot" else None
    if sheet is None or sheet.character_id != owner.incarnation:
        return
    frame = sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(sheet.character_id)
    if frame != value.caster_frame:
        return  # A parked Frame's corruption does not transform a new assigned Frame.
    facts = [
        x
        for x in state.facts
        if x.get("kind") == "living_battery_frame_corruption"
        and x.get("link") == value.id
        and x.get("event") == event
    ]
    if len(facts) != 1 or not json.loads(facts[0]["newly_void"]):
        return
    family = [x for x in sheet.assets if x.family == "frame"]
    if not family or not all(x.void for x in family):
        raise WorkflowError("Recover the actual nonempty newly all-Void Frame family")
    identity = str(uuid5(NAMESPACE_URL, "girlframe:janus-battery-void:" + value.id))
    related(
        c,
        game.store,
        dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
        identity,
        int(owner.entity),
        int(owner.entity),
        "void_threshold",
        dict(
            reason="janus_battery",
            owner=owner.model_dump(mode="json"),
            character=owner.incarnation,
            source_action=action["id"],
            source_pdf=19,
            janus_source_pdf=69,
            immediate=True,
            link=value.id,
            frame=value.caster_frame,
            source_event=event,
            details=dict(family="frame"),
        ),
        event,
    )
    meta["void_work"] = identity
    game.request(c, action, int(owner.entity), "janus_void_threshold", dict(work_id=identity))
    game.save_action(c, action)
    updated, threshold = prepare_threshold(c, game, identity)
    opened = game.event(
        c,
        value.caster_controller,
        str(uuid4()),
        "m3.janus_void_opened",
        updated,
        work_id=identity,
        source_event=event,
    )
    if threshold.stage == "prevented":
        from girlframe.services.m3_void import _append

        works = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(works)
                .where(works.c.campaign_id == game.store.campaign_id, works.c.id == identity)
                .order_by(works.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        _append(
            c,
            dict(row),
            opened,
            json.loads(row["body_json"])
            | dict(threshold=threshold.id, resolution=threshold.stage, actual_actor=None),
            resolved=True,
        )
        complete_void_continuation(game, c, identity, opened, None, str(uuid4()))


def prove_void_source(
    game: GameService, c: Connection, first: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    state = _history(game, c, first["event_id"])
    value = prove_link(game, c, state, body["link"])
    action = game.action(c, value.source_action)
    source = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == first["event_id"]
            )
        )
        .mappings()
        .one()
    )
    history = t.m2["m2_state_history"]
    raw_before = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq < source["seq"])
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    before = GameState.model_validate_json(raw_before) if raw_before else None
    tags = rules.battery_tags(before, value.battery) if before else ()
    fact = next(
        (
            x
            for x in state.facts
            if x.get("kind") == "living_battery_frame_corruption"
            and x.get("link") == value.id
            and x.get("event") == first["event_id"]
        ),
        None,
    )
    response = c.scalar(
        sa.select(t.m2["m2_responses"].c.choice_id)
        .join(
            t.m2["m2_choices"],
            sa.and_(
                t.m2["m2_choices"].c.campaign_id == t.m2["m2_responses"].c.campaign_id,
                t.m2["m2_choices"].c.id == t.m2["m2_responses"].c.choice_id,
            ),
        )
        .where(
            t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_responses"].c.event_id == first["event_id"],
            t.m2["m2_responses"].c.actor_id == str(value.caster_controller),
            t.m2["m2_choices"].c.kind == "janus_erase",
            t.m2["m2_choices"].c.action_id == value.source_action,
        )
    )
    if (
        actor != value.caster_frame_owner
        or value.tier != "low"
        or len(tags) != 1
        or value.erased_tag != tags[0][0]
        or value.erasure_before_tags != tuple(x[0] for x in tags)
        or value.erasure_event != first["event_id"]
        or value.frame_takeover != first["event_id"]
        or rules.battery_tags(state, value.battery)
        or fact is None
        or not json.loads(fact["newly_void"])
        or source["kind"] != "m3.choice_resolved"
        or source["actor_id"] != str(value.caster_controller)
        or response is None
        or body["source_action"] != action["id"]
        or body["frame"] != value.caster_frame
        or body["source_event"] != first["event_id"]
        or first["scene_id"] != action["scene_id"]
        or first["campaign_context"]
        or action["data"]["janus"].get("void_work") != first["id"]
    ):
        raise WorkflowError("Prove the actual final-Tag erasure and newly corrupted original Frame")


def complete_void_continuation(
    game: GameService,
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.engine.m3_void import FINAL

    works = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(works)
            .where(works.c.campaign_id == game.store.campaign_id, works.c.id == identity)
            .order_by(works.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .one()
    )
    body = json.loads(row["body_json"])
    state = load_state(c, game.store.campaign_id)
    value = prove_link(game, c, state, body["link"])
    action = game.action(c, value.source_action)
    if (
        row["state"] != "resolved"
        or action["data"]["janus"].get("void_work") != identity
        or not any(
            identity in x.source_works and x.actor == value.caster_frame_owner and x.stage in FINAL
            for x in state.void_thresholds
        )
    ):
        raise WorkflowError("Finish only this actual original Frame's real Void consequence")
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.action_id == action["id"],
            choices.c.kind == "janus_void_threshold",
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    _finish(game, c, state, action)
    game.save_action(c, action)


def complete_ended_link(game: GameService, c: Connection, link: BatteryLink, event: str) -> None:
    """A real original ending closes impossible responses without inventing an answer."""
    state = load_state(c, game.store.campaign_id)
    value = prove_link(game, c, state, link.id)
    if value.phase != "ended" or value.end_event != event:
        raise WorkflowError("Only this link's actual source-proved original ending can close it")
    action = game.action(c, value.source_action)
    if action["data"].get("janus", {}).get("link") != value.id:
        raise WorkflowError("Recover the original actual Living Battery action")
    if action["state"] in ("complete", "aborted"):
        return
    choices = t.m2["m2_choices"]
    for row in game.pending(c, action["id"]):
        if row["kind"] not in ("janus_erase", "janus_select", "janus_answer", "tag_window"):
            continue
        c.execute(
            choices.update()
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == row["id"],
                choices.c.revision == row["revision"],
            )
            .values(state="completed_by_work", revision=row["revision"] + 1)
        )
    action["data"]["janus"]["original_ended_event"] = event
    _finish(game, c, state, action)
    game.save_action(c, action)


def visible_result(
    result: dict[str, Any], meta: dict[str, Any], viewer: GuildViewer, state: GameState
) -> dict[str, Any]:
    value = rules.get(state, meta["link"]) if meta.get("link") else None
    public = {k: v for k, v in result.items() if k in ("tier", "total")}
    if value is not None and viewer.user_id in (value.caster_controller, value.battery_controller):
        public["brain_question"] = value.question
        public["brain_answer"] = value.answer
    return public


def preview(
    game: GameService, viewer: GuildViewer, channel: int, target: ActorRef | None = None
) -> dict[str, Any]:
    """Only actual known source roles are offered; contact still needs its own proof."""
    from girlframe.engine.m3_janus_requisitions import UNIVERSAL
    from girlframe.services.m3_janus_requisitions import owned

    try:
        with game.store.engine.connect() as c:
            authorize(game, c, viewer)
            state = load_state(c, game.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            sheet = state.sheets[actor.entity]
            if sheet.frame not in ("JANUS", "JANUS-B"):
                return dict(available=False)
            actual = resolve(state, actor, profiles(c, game.store.campaign_id))
            core = bound(state, actor, str(actual.frame_instance))
            cast = _cast(game, c, state, channel)
            refs = []
            if core is not None and core.alive:
                refs.append(ref(core))
            if owned(c, game, state, actor, UNIVERSAL):
                refs.extend(x.actor for x in cast.roles if x.actor != actor)
            targets = []
            for body in dict.fromkeys(refs):
                view = resolve(
                    state, body, profiles(c, game.store.campaign_id), require_current_profile=False
                )
                if view.alive:
                    targets.append(
                        dict(ref=body.model_dump(mode="json"), token=body.token, label=view.label)
                    )
            if not targets:
                return dict(available=False)
            selected = target or ActorRef.model_validate(targets[0]["ref"])
            if selected.model_dump(mode="json") not in [x["ref"] for x in targets]:
                raise WorkflowError("Select an actual available source battery")
            try:
                contact = prepare_battery(game, c, state, actor, selected, channel)
            except WorkflowError:
                contact = None
            linked = next(
                (
                    x
                    for x in state.battery_links
                    if contact is not None and x.connection == contact["connection"]
                ),
                None,
            )
            return dict(
                available=True,
                actor=actor.model_dump(mode="json"),
                target=selected.model_dump(mode="json"),
                targets=targets,
                connection=contact,
                rolled=linked is not None,
                sheet_revision=sheet.revision,
                link=linked.id if linked else None,
            )
    except (ValueError, WorkflowError):
        return dict(available=False)


class BatteryService:
    """Free private communication uses the real selected brain-link option, never chat ingestion."""

    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _get(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, BatteryLink]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        value = prove_link(self.game, c, state, identity)
        if viewer.user_id not in (value.caster_controller, value.battery_controller):
            raise WorkflowError("This brain conversation belongs only to its two actual minds")
        if "question" not in value.selected or not value.effects_event:
            raise WorkflowError("This actual roll did not select direct brain communication")
        return state, value

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, value = self._get(c, viewer, identity)
            can_send = value.phase == "connected"
            if can_send:
                try:
                    assert value.connection is not None
                    actual = prove_contact(self.game, c, state, value.connection)
                    can_send = actual.phase == "connected"
                except WorkflowError:
                    can_send = False
            return dict(
                id=value.id,
                revision=state.revision,
                phase=value.phase,
                question=value.question,
                answer=value.answer,
                messages=[x.model_dump(mode="json") for x in value.messages],
                actors=[
                    x.model_dump(mode="json")
                    for x, owner in (
                        (value.caster, value.caster_controller),
                        (value.battery, value.battery_controller),
                    )
                    if owner == viewer.user_id
                ],
                can_send=can_send,
            )

    def send(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        actor: ActorRef,
        text: str,
    ) -> dict[str, Any]:
        if not text.strip() or len(text) > 1200:
            raise WorkflowError("Write your own bounded private brain message")

        def authorize_write(c: Connection) -> None:
            authorize(self.game, c, viewer)
            self._get(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._get(c, viewer, identity)
            if state.revision != revision or value.phase != "connected":
                raise WorkflowError("Refresh the actual active brain-link conversation")
            assert value.connection is not None
            contact = prove_contact(self.game, c, state, value.connection)
            if contact.phase != "connected":
                raise WorkflowError("An ended neural connection carries no new brain messages")
            allowed = {
                ref
                for ref, owner in (
                    (value.caster, value.caster_controller),
                    (value.battery, value.battery_controller),
                )
                if owner == viewer.user_id
            }
            if actor not in allowed:
                raise WorkflowError("Speak only for your actual original linked mind")
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actual.controller != viewer.user_id or not actual.alive:
                raise WorkflowError("No successor or other body inherits this private channel")
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(
                    update={
                        "messages": (
                            *value.messages,
                            BrainMessage(
                                actor=actor,
                                controller=viewer.user_id,
                                text=text.strip(),
                                source_event=event,
                            ),
                        )
                    }
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.janus_mind_message",
                state,
                event_id=event,
                link=value.id,
            )
            return dict(id=value.id, source_event=event)

        return self.store._write(
            viewer,
            key,
            "m3.janus_mind_message",
            dict(link=identity, actor=actor.model_dump(mode="json"), text=text.strip()),
            operation,
            auto_audit=False,
            authorize=authorize_write,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id, revision=state.revision, phase=x.phase, actionable=x.phase == "connected")
            for x in state.battery_links
            if "question" in x.selected
            and x.phase in ("question", "connected")
            and viewer.user_id in (x.caster_controller, x.battery_controller)
        ]
