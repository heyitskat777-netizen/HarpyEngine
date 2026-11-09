"""Real voluntary Princess source, owned outcomes and one actual counterpart child."""

import json
from typing import Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_princess_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, tier
from girlframe.engine.m3_actor_bonds import change, current_ref, depth, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_handler_pr import _audit
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "princess_sex_low_tag",
    "princess_sex_favour",
    "princess_sex_favour_reply",
    "princess_sex_optional_tag",
    "princess_sex_direct",
    "princess_sex_child",
)


def _copy(state: GameState, updated: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(updated, key))


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _contact(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    channel: int,
    *,
    bonded_source: str | None = None,
    changeling_source: str | None = None,
    learned_source: str | None = None,
    lesson_id: str | None = None,
    pending_event: str | None = None,
) -> None:
    from girlframe.services.m3_bonded import admit_delegation
    from girlframe.services.m3_changeling_sex import admit_contact

    if (
        sum(x is not None for x in (changeling_source, bonded_source, learned_source, lesson_id))
        > 1
    ):
        raise WorkflowError("Keep actual psychic contact separate from Bonded delegation")
    remote = admit_contact(game, c, state, actor, target, rules.RULE, changeling_source)
    from girlframe.services.m3_learned_sex import admit_offer, admit_source

    learned = (
        admit_source(
            game, c, state, actor, target, rules.RULE, learned_source, pending_event=pending_event
        )
        if learned_source
        else admit_offer(game, c, state, actor, rules.RULE, lesson_id)
    )

    if actor.kind != "pilot" or target.kind != "pilot" or actor == target:
        raise WorkflowError("This interaction needs two actual original native Girls")
    bound = profiles(c, game.store.campaign_id)
    own, other = resolve(state, actor, bound), resolve(state, target, bound)
    cast = _cast(game, c, state, channel)
    if (
        cast.adjudicator is not None
        or not (
            (has_rule(state.sheets[actor.entity], rules.RULE, "PRINCESS") or learned)
            if bonded_source is None
            else admit_delegation(game, c, state, actor, target, rules.RULE, bonded_source)
        )
        or any(
            x.offstage_source
            or x.custody not in (None, "free")
            or x.rules != "girl_frame"
            or (not remote and x.inside_frame is not False)
            or (not remote and x.cell is None)
            for x in (own, other)
        )
        or (not remote and own.cell != other.cell)
        or any(
            state.sheets[x.entity].medical_state != "fit" or is_helpless(state, x)
            for x in (actor, target)
        )
        or not all(
            any(r.actor == ref and r.controller == int(ref.entity) for r in cast.roles)
            for ref in (actor, target)
        )
    ):
        raise WorkflowError(
            "Use the actual available Princess and counterpart together outside their Frames"
        )


def _event(
    game: GameService,
    c: Connection,
    event: str,
    kinds: tuple[str, ...],
    actor: int | None = None,
    action: str | None = None,
) -> None:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["kind"] not in kinds
        or actor is not None
        and row["actor_id"] != str(actor)
        or action is not None
        and json.loads(row["payload_json"]).get("action_id") != action
    ):
        raise WorkflowError("Recover the actual immutable Princess source and real human author")


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Session:
    value = rules.get(state, identity)
    if value.learned_source is not None:
        from girlframe.services.m3_learned_sex import prove as prove_lesson

        link = prove_lesson(game, c, state, value.learned_source)
        if (
            link.rule_id != rules.RULE
            or link.session != value.id
            or link.actor != value.actor
            or link.target != value.target
        ):
            raise WorkflowError("Preserve this exact original learned Princess source")
    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import prove_source_link

        prove_source_link(
            game, c, state, value.changeling_source, value.id, value.actor, value.target, rules.RULE
        )

    born = rules.get(_history(c, game, value.proposed_event), identity)
    from girlframe.services.m3_bonded import prove_delegation

    prove_delegation(
        game, c, state, value.bonded_source, value.id, value.actor, value.target, rules.RULE
    )
    stable = (
        "id",
        "actor",
        "target",
        "caster",
        "counterpart",
        "cast",
        "registry",
        "proposed_event",
        "proposal",
        "bonded_source",
        "changeling_source",
        "learned_source",
    )
    _audit(game, c, value.proposed_event, "m3.princess_sex_invited", str(value.caster))
    if any(getattr(value, k) != getattr(born, k) for k in stable):
        raise WorkflowError(
            "Preserve the actual original participants and disclosed interaction source"
        )
    if value.consent_event:
        consent = rules.get(_history(c, game, value.consent_event), identity)
        _audit(game, c, value.consent_event, "m3.princess_sex_consent", str(value.counterpart))
        if (
            consent.phase not in ("accepted", "declined")
            or consent.consent_account != value.consent_account
            or any(getattr(consent, k) != getattr(value, k) for k in stable)
        ):
            raise WorkflowError(
                "Only the actual counterpart's own source reply establishes this interaction"
            )
    if value.bound_event:
        bound = rules.get(_history(c, game, value.bound_event), identity)
        _event(
            game,
            c,
            value.bound_event,
            ("m2.play_confirmed", "m3.play_confirmed"),
            value.caster,
            value.action,
        )
        if bound.action != value.action or bound.phase != "active" or not value.consent_event:
            raise WorkflowError("Recover the actual accepted source's original bound Play")
    if value.effect_event:
        original = _history(c, game, value.effect_event)
        effect = rules.get(original, identity)
        action = game.action(c, value.action or "")
        raw = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == value.action,
            )
        )
        _event(
            game,
            c,
            value.effect_event,
            ("m2.choice_resolved", "m3.choice_resolved"),
            action=value.action,
        )
        if (
            raw is None
            or json.loads(raw) != action["data"].get("receipt")
            or action["data"].get("princess_sex", {}).get("session") != value.id
            or effect.effect_event != value.effect_event
            or effect.tier != value.tier
        ):
            raise WorkflowError("Recover the actual saved Princess roll and printed result")
        total = json.loads(raw)["pre_total"] + sum(x["amount"] for x in action["data"]["modifiers"])
        from girlframe.services.m3_gender_designation import prove_man_result

        minimum = prove_man_result(game, c, original, action)
        if tier(max(total, minimum or total)) != value.tier:
            raise WorkflowError(
                "A Princess result needs its actual unchanged roll and proved modifiers"
            )
    for event, fields, author in (
        (value.favour_event, ("favour",), value.caster),
        (value.response_event, ("response", "response_account"), value.counterpart),
        (value.tag_event, ("tag",), value.counterpart if value.tier == "low" else value.caster),
    ):
        if event:
            saved = rules.get(_history(c, game, event), identity)
            _event(
                game, c, event, ("m2.choice_resolved", "m3.choice_resolved"), author, value.action
            )
            if any(getattr(saved, k) != getattr(value, k) for k in fields):
                raise WorkflowError("Preserve each actual owned Princess result decision")
    return value


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    _access(game, c, viewer)
    value = prove(game, c, state, prepared.source_work or "")
    if (
        value.phase != "accepted"
        or value.caster != viewer.user_id
        or prepared.target_actor != value.target
        or prepared.parent
        or prepared.target is not None
        or prepared.order_id
        or prepared.off_duty_id
        or not prepared.context.strip()
        or not prepared.trigger_confirmed
    ):
        raise WorkflowError("Use this original accepted voluntary Princess source")
    _contact(
        game,
        c,
        state,
        value.actor,
        value.target,
        channel,
        bonded_source=value.bonded_source,
        changeling_source=value.changeling_source,
        learned_source=value.learned_source,
    )
    if fingerprint(_cast(game, c, state, channel)) != fingerprint(value.cast):
        raise WorkflowError("The actual accepted source cast changed")
    return (
        dict(
            session=value.id,
            actor=value.actor.model_dump(mode="json"),
            target=value.target.model_dump(mode="json"),
            cast=value.cast.model_dump(mode="json"),
            cast_sha256=fingerprint(value.cast),
            table=sorted(
                {r.controller for r in value.cast.roles}
                | ({value.cast.facilitator} if value.cast.facilitator else set())
            ),
            caster=value.caster,
            counterpart=value.counterpart,
        )
        | ({"learned_source": value.learned_source} if value.learned_source is not None else {})
        | ({"bonded_source": value.bonded_source} if value.bonded_source is not None else {})
        | (
            {"changeling_source": value.changeling_source}
            if value.changeling_source is not None
            else {}
        )
    )


def bind(state: GameState, action: dict[str, Any], event: str | None = None) -> None:
    value = rules.get(state, action["data"]["princess_sex"]["session"])
    if value.phase != "accepted" or value.action or not event:
        raise WorkflowError(
            "Bind this accepted original interaction once to its actual confirmation event"
        )
    rules.put(
        state, value.model_copy(update=dict(action=action["id"], bound_event=event, phase="active"))
    )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    value = prove(
        game, c, load_state(c, game.store.campaign_id), action["data"]["princess_sex"]["session"]
    )
    if (
        value.action != action["id"]
        or viewer.user_id not in action["data"]["princess_sex"]["table"]
    ):
        raise WorkflowError("Only the original source-table human owns this Princess response")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    value = rules.get(state, action["data"]["princess_sex"]["session"])
    if viewer.user_id != value.caster or value.phase != "active" or value.effect_event:
        raise WorkflowError("Roll the actual original Princess source once")
    _contact(
        game,
        c,
        state,
        value.actor,
        value.target,
        value.cast.channel,
        bonded_source=value.bonded_source,
        changeling_source=value.changeling_source,
        learned_source=value.learned_source,
    )


def _finish(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str | None = None,
) -> None:
    if game.pending(c, action["id"]) or action["state"] == "complete":
        return
    from girlframe.services.m2_choices import ChoiceEngine

    value = rules.get(state, action["data"]["princess_sex"]["session"])
    rules.put(
        state,
        value.model_copy(
            update=dict(phase="complete", completed_event=event or action["data"]["response_event"])
        ),
    )
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.get(state, action["data"]["princess_sex"]["session"])
    if value.effect_event:
        raise WorkflowError("Resume the actual saved Princess result; never duplicate it")
    from girlframe.services.m3_gender_designation import offer_animal_tags

    if offer_animal_tags(game, c, state, action):
        action["data"]["gender_sex_deferred"] = True
        return
    level, event = action["data"]["result"]["tier"], action["data"]["response_event"]
    changes: dict[str, Any] = dict(effect_event=event, tier=level)
    if level == "low":
        old = depth(state, value.actor, value.target)
        _copy(state, change(state, value.actor, value.target, -1, event))
        changes.update(
            phase="low_tag", bond_before=old, bond_after=depth(state, value.actor, value.target)
        )
        game.request(c, action, value.counterpart, "princess_sex_low_tag")
    elif level == "mid":
        changes["phase"] = "favour"
        game.request(c, action, value.caster, "princess_sex_favour")
    else:
        changes["phase"] = "direction"
        game.request(c, action, value.caster, "princess_sex_direct")
    rules.put(state, value.model_copy(update=changes))


def _strict(answer: ChoiceAnswer, options: tuple[str, ...] = (), text: bool = False) -> None:
    if (
        answer.options != options
        or answer.denied
        or answer.fields
        or answer.number is not None
        or answer.flag is not None
        or answer.member is not None
        or (not answer.text.strip() if text else bool(answer.text))
    ):
        raise WorkflowError("Use only this actual owned Princess decision")


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    value = prove(game, c, state, action["data"]["princess_sex"]["session"])
    event, kind = action["data"]["response_event"], row["kind"]
    if kind == "princess_sex_child":
        raise WorkflowError("Make the actual selected child Play; acknowledgment cannot replace it")
    if kind in ("princess_sex_low_tag", "princess_sex_optional_tag"):
        expected = value.counterpart if kind == "princess_sex_low_tag" else value.caster
        if int(row["actor_id"]) != expected:
            raise WorkflowError("Only the actual printed giver authors this ordinary Tag")
        if kind == "princess_sex_optional_tag" and answer.options == ("decline",):
            _strict(answer, ("decline",))
        else:
            _strict(answer, ("give",) if kind == "princess_sex_optional_tag" else (), text=True)
            from girlframe.engine.m3_mockingbird import give_tag

            giver, target = (
                (value.target, value.actor) if value.tier == "low" else (value.actor, value.target)
            )
            tag = str(uuid4())
            _copy(
                state,
                give_tag(
                    state,
                    profiles(c, game.store.campaign_id),
                    target,
                    giver,
                    answer.text.strip(),
                    tag,
                    event,
                    tuple(action["data"]["participants"]),
                ),
            )
            rules.put(state, value.model_copy(update=dict(tag=tag, tag_event=event)))
        _finish(game, c, state, action)
    elif kind == "princess_sex_favour":
        _strict(answer, text=True)
        rules.put(
            state,
            value.model_copy(
                update=dict(favour=answer.text.strip(), favour_event=event, phase="favour_reply")
            ),
        )
        game.request(c, action, value.counterpart, "princess_sex_favour_reply")
    elif kind == "princess_sex_favour_reply":
        if answer.options not in (("agree",), ("refuse",)):
            raise WorkflowError("Give your own actual response to this specific favour")
        _strict(answer, answer.options, text=True)
        rules.put(
            state,
            value.model_copy(
                update=dict(
                    response=answer.options[0],
                    response_event=event,
                    response_account=answer.text.strip(),
                    phase="optional_tag" if answer.options == ("refuse",) else value.phase,
                )
            ),
        )
        if answer.options == ("refuse",):
            game.request(c, action, value.caster, "princess_sex_optional_tag")
        else:
            _finish(game, c, state, action)
    elif kind == "princess_sex_direct":
        if len(answer.options) != 1 or set(answer.fields) - {"target", "order_id"}:
            raise WorkflowError(
                "Choose one genuine basic directive and only its actual target/Order"
            )
        _strict(answer.model_copy(update={"fields": {}}), answer.options, text=True)
        selected = answer.options[0]
        if selected not in BASIC_PLAYS and selected != "dose_up":
            raise WorkflowError("This required Play needs its own real source-recipe adapter")
        target = None
        if answer.fields.get("target"):
            target = next(
                (x.actor for x in value.cast.roles if x.actor.token == answer.fields["target"]),
                None,
            )
            if target is None:
                raise WorkflowError("Select the actual original scene target")
        order_id = answer.fields.get("order_id") or None
        _prerequisites(game, c, state, value, selected, target, order_id)
        if value.tier != "high" or value.direction or value.phase != "direction":
            raise WorkflowError("Use the actual high Princess result's one legal child")
        direction = rules.HighDirection(
            id=value.id + ":direction",
            session=value.id,
            parent=action["id"],
            actor=value.target,
            actor_controller=value.counterpart,
            author=value.actor,
            author_controller=value.caster,
            source_event=value.effect_event or "",
            selected_choice=row["id"],
            selected_event=event,
            play=cast(Any, selected),
            target=target,
            order_id=order_id,
            context=answer.text.strip(),
        )
        rules.put(state, direction)
        rules.put(state, value.model_copy(update=dict(direction=direction.id, phase="child")))
        game.request(c, action, value.caster, "princess_sex_child", dict(direction=direction.id))
    else:
        raise WorkflowError("Use the exact original Princess source decision")


BASIC_PLAYS = {
    "keep_your_head": "Keep Your Head",
    "check_sensors": "Check Your Sensors",
    "flirt": "Flirt",
    "engage": "Engage",
    "all_out_assault": "All Out Assault — actual reviewed declaration",
    "put_someone_beneath_you": "Put Someone Beneath You",
    "disobey_orders": "Disobey an actual applicable Order",
}


def _applicable_order(
    game: GameService, c: Connection, state: GameState, session: rules.Session, order_id: str | None
) -> dict[str, Any]:
    row = game.valid_order(c, state, session.counterpart, session.cast.channel, order_id)
    actions = t.m2["m2_actions"]
    sources = (
        c.execute(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == game.store.campaign_id,
                sa.func.json_extract(actions.c.body_json, "$.play") == "receive_orders",
                sa.func.json_extract(actions.c.body_json, "$.order_id") == row["id"],
            )
        )
        .scalars()
        .all()
    )
    if len(sources) != 1:
        raise WorkflowError(
            "SOURCE_ORDER_ANCESTRY: retain the actual original Receive Orders source"
        )
    source = game.action(c, sources[0])
    if (
        source["state"] != "complete"
        or game.pending(c, source["id"])
        or source["channel_id"] != str(session.cast.channel)
        or source["scene_id"] != session.cast.id
        or source["actor_id"] != session.target.entity
        or source["data"].get("character_ids", {}).get(session.target.entity)
        != session.target.incarnation
    ):
        raise WorkflowError(
            "SOURCE_ORDER_ANCESTRY: finish the real Receive Orders chain before this directive"
        )
    birth = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m2.order_issued",
        )
    ).all()
    if not any(
        x.actor_id == row["issuer_id"]
        and json.loads(x.payload_json).get("action_id") == source["id"]
        for x in birth
    ):
        raise WorkflowError("Recover the real canonical Order issuance before directing refusal")
    return row


def _prerequisites(
    game: GameService,
    c: Connection,
    state: GameState,
    session: rules.Session,
    play: str,
    target: ActorRef | None,
    order_id: str | None,
) -> None:
    if play not in BASIC_PLAYS and play != "dose_up":
        raise WorkflowError("This directive needs a separate actual source-recipe adapter")
    _contact(
        game,
        c,
        state,
        session.actor,
        session.target,
        session.cast.channel,
        bonded_source=session.bonded_source,
        changeling_source=session.changeling_source,
        learned_source=session.learned_source,
    )
    current = _cast(game, c, state, session.cast.channel)
    if fingerprint(current) != fingerprint(session.cast):
        raise WorkflowError("STALE_CAST: retain the actual original Princess source scene")
    performer = resolve(state, session.target, profiles(c, game.store.campaign_id))
    if not performer.alive or performer.ref != current_ref(state, session.counterpart):
        raise WorkflowError("Use the original living counterpart, never an account replacement")
    if play == "dose_up":
        from girlframe.engine.m3_dose_up import RULE as dose_rule
        from girlframe.services.m3_dose_up import _operator

        sheet = state.sheets.get(session.target.entity)
        if (
            target is not None
            or order_id is not None
            or sheet is None
            or sheet.girl != "STIM-BLISSED"
            or not has_rule(sheet, dose_rule, "STIM-BLISSED")
        ):
            raise WorkflowError("Direct only the actual native Stim's owned self-Dose")
        _operator(game, c, state, session.target)
        gate = Access(game.store).registry
        if gate is None:
            raise WorkflowError("Recover the actual reviewed Dose Up source")
        gate.require_available(dose_rule)
        return
    targeted = play in ("flirt", "engage", "all_out_assault", "put_someone_beneath_you")
    if targeted != (target is not None) or target == session.target:
        raise WorkflowError("Choose this actual basic Play's distinct real target")
    if target is not None:
        actual = resolve(state, target, profiles(c, game.store.campaign_id))
        if (
            not actual.alive
            or actual.offstage_source
            or not any(
                x.actor == target and x.controller == actual.controller for x in current.roles
            )
        ):
            raise WorkflowError("The real target must still belong to this actual source scene")
        if play == "flirt" and target.kind == "npc":
            from girlframe.services.m3_battle import _visible
            from girlframe.services.m3_npc_flirt import _npc

            _npc(state, target)
            if not _visible(state, target, session.counterpart):
                raise WorkflowError("Use a counterpart visible to the actual performing Girl")
        elif play in ("flirt", "put_someone_beneath_you") and (
            target.kind != "pilot" or current_ref(state, int(target.entity)) != target
        ):
            raise WorkflowError("This basic child requires its actual supported target adapter")
        if play == "all_out_assault" and not any(not x.damaged for x in actual.assets):
            raise WorkflowError(
                "Assault needs an actual opposing undamaged Asset and reviewed opening"
            )
    if play == "engage" and not any(not x.damaged for x in performer.assets):
        raise WorkflowError("Engage requires the performer's actual usable owned Asset")
    if play == "disobey_orders":
        _applicable_order(game, c, state, session, order_id)
        from girlframe.engine.m3_am import require_freedom

        require_freedom(state, session.target, "refuse")
    elif order_id is not None:
        raise WorkflowError("Only actual Disobey uses an existing Order; no source fabrication")


def directive_options(
    game: GameService, c: Connection, state: GameState, session_id: str
) -> dict[str, Any]:
    session = prove(game, c, state, session_id)
    targets = []
    bound = profiles(c, game.store.campaign_id)
    for role in session.cast.roles:
        if role.actor == session.target:
            continue
        actual = resolve(state, role.actor, bound)
        if not actual.alive or actual.offstage_source or actual.controller != role.controller:
            continue
        allowed = []
        for play in ("flirt", "put_someone_beneath_you", "engage", "all_out_assault"):
            try:
                _prerequisites(game, c, state, session, play, role.actor, None)
            except (WorkflowError, ValueError):
                continue
            allowed.append(play)
        if allowed:
            targets.append(
                dict(
                    ref=role.actor.model_dump(mode="json"),
                    token=role.actor.token,
                    label=actual.label,
                    plays=allowed,
                )
            )
    orders: list[dict[str, str]] = []
    table = t.m2["m2_orders"]
    for row in c.execute(
        sa.select(table).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.channel_id == str(session.cast.channel),
            table.c.target_id == str(session.counterpart),
            table.c.state == "disobey",
        )
    ).mappings():
        try:
            _prerequisites(game, c, state, session, "disobey_orders", None, row["id"])
        except (WorkflowError, ValueError):
            continue
        # No private Order prose is projected merely because it exists.
        orders.append(
            dict(id=row["id"], label="Actual already-received Order " + str(len(orders) + 1))
        )
    plays = []
    for play, label in BASIC_PLAYS.items():
        if (
            play in ("keep_your_head", "check_sensors")
            or (play == "disobey_orders" and orders)
            or any(play in x["plays"] for x in targets)
        ):
            plays.append(dict(id=play, label=label))
    try:
        _prerequisites(game, c, state, session, "dose_up", None, None)
    except (ValueError, WorkflowError):
        pass
    else:
        plays.append(dict(id="dose_up", label="Own native Stim self-Dose Up"))
    return dict(plays=plays, targets=targets, orders=orders)


def _prepared_target(value: rules.HighDirection, prepared: PlayInput) -> bool:
    if value.target is None:
        return prepared.target is None and prepared.target_actor is None
    if value.play == "flirt" and value.target.kind == "npc":
        return prepared.target is None and prepared.target_actor == value.target
    if value.play in ("flirt", "put_someone_beneath_you"):
        return prepared.target == int(value.target.entity) and prepared.target_actor in (
            None,
            value.target,
        )
    return prepared.target is None and prepared.target_actor == value.target


def child_projection(
    game: GameService, c: Connection, state: GameState, direction_id: str
) -> dict[str, Any]:
    value = _direction(game, c, state, direction_id)
    session = rules.get(state, value.session)
    sheet = state.sheets.get(value.actor.entity)
    if sheet is None or sheet.character_id != value.actor.incarnation:
        raise WorkflowError("Recover this original counterpart's actual source sheet")
    pending = next(
        (x for x in game.pending(c, value.parent) if x["kind"] == "princess_sex_child"), None
    )
    from girlframe.engine.m3_clone_am import additional_identities
    from girlframe.services.m3_clone_am import prove_additional
    from girlframe.services.m3_dampener import entitlement as dampener_entitlement
    from girlframe.services.m3_kicked_puppy import entitlement as kicked_entitlement
    from girlframe.services.m3_nightmare import entitlement

    extra = additional_identities(state, sheet.owner)
    if extra:
        prove_additional(game, c, state, sheet.owner)
    actual = resolve(state, value.actor, profiles(c, game.store.campaign_id))
    descriptor: dict[str, Any] = dict(
        kind="princess_sex_child",
        parent=value.parent,
        channel=session.cast.channel,
        actor=value.actor.model_dump(mode="json"),
        choice=pending["id"] if pending else None,
        body=dict(
            actor=value.actor.model_dump(mode="json"),
            source_work=value.id,
            play=value.play,
            target=value.target.model_dump(mode="json") if value.target else None,
            order_id=value.order_id,
            context=value.context,
        ),
    )
    return dict(
        id=value.id,
        direction=value.id,
        session=value.session,
        actor=value.actor.model_dump(mode="json"),
        actor_controller=value.actor_controller,
        author=value.author_controller,
        play=value.play,
        target=descriptor["body"]["target"],
        order_id=value.order_id,
        parent=value.parent,
        choice=descriptor["choice"],
        source_work=value.id,
        channel=session.cast.channel,
        context=value.context,
        sheet_revision=sheet.revision,
        heat=sheet.heat,
        identities=[x.model_dump(mode="json") for x in sheet.identities if not x.marked],
        additional_identities=[x.model_dump(mode="json") for x in extra if not x.marked],
        disposable=has_rule(sheet, "girl.stim-blissed.disposable-psyche", "STIM-BLISSED"),
        assets=[x.model_dump(mode="json") for x in actual.assets],
        piloting=actual.piloting,
        nightmare=bool(entitlement(game, c, state, value.actor)),
        kicked_puppy=value.play == "flirt"
        and value.target is not None
        and value.target.kind == "pilot"
        and bool(kicked_entitlement(game, c, state, value.actor)),
        dampener=bool(dampener_entitlement(game, c, state, value.actor)),
        child=value.child,
        descriptor=descriptor,
    )


def pre_roll_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    value = _bound(game, c, state, action)
    if value is None:
        return
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    if (
        prepared.play != value.play
        or prepared.context != value.context
        or prepared.source_work != value.id
        or prepared.parent != value.parent
        or prepared.order_id != value.order_id
        or not _prepared_target(value, prepared)
        or value.completed_event
    ):
        raise WorkflowError("Preserve the actual frozen directive, target and Order before dice")
    _prerequisites(
        game, c, state, rules.get(state, value.session), value.play, value.target, value.order_id
    )


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = prove(game, c, state, action["data"]["princess_sex"]["session"])
    return dict(
        session=value.id,
        favour=value.favour,
        direction=value.direction,
        **directive_options(game, c, state, value.id),
    )


def _direction(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.HighDirection:
    value = rules.direction(state, identity)
    session = prove(game, c, state, value.session)
    original = rules.direction(_history(c, game, value.selected_event), identity)
    stable = tuple(
        k
        for k in rules.HighDirection.model_fields
        if k not in ("child", "bound_event", "completed_event")
    )
    _event(
        game,
        c,
        value.selected_event,
        ("m2.choice_resolved", "m3.choice_resolved"),
        value.author_controller,
        value.parent,
    )
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.id == value.selected_choice,
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
            )
        )
        .mappings()
        .first()
    )
    if (
        any(getattr(value, k) != getattr(original, k) for k in stable)
        or session.tier != "high"
        or session.effect_event != value.source_event
        or session.action != value.parent
        or session.direction != value.id
        or (value.actor, value.actor_controller, value.author, value.author_controller)
        != (session.target, session.counterpart, session.actor, session.caster)
        or row is None
        or row["kind"] != "princess_sex_direct"
        or row["actor_id"] != str(value.author_controller)
        or row["action_id"] != value.parent
        or row["state"] != "answered"
    ):
        raise WorkflowError("Recover the genuine original high source and fixed decision author")
    if value.bound_event:
        bound = rules.direction(_history(c, game, value.bound_event), identity)
        _event(
            game,
            c,
            value.bound_event,
            ("m2.play_confirmed", "m3.play_confirmed"),
            value.author_controller,
            value.child,
        )
        if bound.child != value.child or bound.actor != value.actor or bound.author != value.author:
            raise WorkflowError("Preserve the actual single child and real source author")
    if value.completed_event:
        completed = rules.direction(_history(c, game, value.completed_event), identity)
        if completed != value or game.action(c, value.child or "")["state"] != "complete":
            raise WorkflowError("The directive expires only after its actual child completion")
        completion_audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == value.completed_event,
                )
            )
            .mappings()
            .one()
        )
        if completion_audit["kind"] == "m3.princess_directed_npc_flirt_completed":
            from girlframe.services.m3_princess_performer import prove_npc_flirt_completion

            prove_npc_flirt_completion(game, c, value, completion_audit)
            return value
        if completion_audit["kind"] == "m3.princess_directed_battle_completed":
            from girlframe.services.m3_princess_performer import prove_battle_completion

            prove_battle_completion(game, c, value, completion_audit)
            return value
        _event(
            game,
            c,
            value.completed_event,
            ("m2.choice_resolved", "m3.choice_resolved"),
            action=value.child,
        )
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == value.completed_event,
                )
            )
            .mappings()
            .one()
        )
        choice_id = json.loads(audit["payload_json"]).get("choice_id")
        choice = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.id == choice_id,
                )
            )
            .mappings()
            .first()
        )
        if (
            choice is None
            or choice["action_id"] != value.child
            or choice["state"] != "answered"
            or audit["actor_id"]
            != str(
                value.author_controller
                if _performer_row(value, game.action(c, value.child or ""), dict(choice))
                else choice["actor_id"]
            )
        ):
            raise WorkflowError(
                "Retain the actual child completion response and its true human author"
            )
    return value


def child_source(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not prepared.source_work or not any(
        x.id == prepared.source_work for x in rules.directions(state)
    ):
        return None
    _access(game, c, viewer)
    value = _direction(game, c, state, prepared.source_work)
    session = rules.get(state, value.session)
    parent = game.action(c, value.parent)
    pending = next(
        (x for x in game.pending(c, value.parent) if x["kind"] == "princess_sex_child"), None
    )
    if (
        viewer.user_id != value.author_controller
        or value.child
        or value.completed_event
        or prepared.parent != value.parent
        or prepared.context != value.context
        or prepared.play != value.play
        or channel != session.cast.channel
        or prepared.order_id != value.order_id
        or prepared.off_duty_id
        or not _prepared_target(value, prepared)
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
        or parent["state"] == "complete"
        or pending is None
    ):
        raise WorkflowError(
            "Only the original Princess directs this fixed counterpart's actual single legal child"
        )
    _prerequisites(game, c, state, session, value.play, value.target, value.order_id)
    return dict(
        direction=value.id,
        session=value.session,
        parent=value.parent,
        actor=value.actor.model_dump(mode="json"),
        actor_controller=value.actor_controller,
        author=value.author_controller,
        target=value.target.model_dump(mode="json") if value.target else None,
        order_id=value.order_id,
        play=value.play,
        context=value.context,
        source_work=value.id,
        channel=session.cast.channel,
        choice=pending["id"],
        cast=session.cast.model_dump(mode="json"),
        table=sorted(
            {x.controller for x in session.cast.roles}
            | ({session.cast.facilitator} if session.cast.facilitator else set())
        ),
    )


def controlled_dose(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    prepared: PlayInput,
    channel: int,
    *,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Positive original directive, not a proxy viewer or new Dose entitlement."""
    if prepared.play != "dose_up" or not prepared.source_work:
        return None
    candidate = next((x for x in rules.directions(state) if x.id == prepared.source_work), None)
    if candidate is None:
        return None
    if candidate.play != "dose_up":
        raise WorkflowError("Use the actual selected self-Dose directive")
    if action is None:
        return child_source(game, c, viewer, state, prepared, channel)
    value = _bound(game, c, state, action)
    if (
        value is None
        or value.id != candidate.id
        or value.completed_event
        or viewer.user_id != value.author_controller
        or channel != rules.get(state, value.session).cast.channel
        or prepared.model_dump()
        != PlayInput.model_validate_json(json.dumps(action["data"]["prepared"])).model_dump()
    ):
        raise WorkflowError("Reopen the exact actual bound self-Dose and original Princess author")
    pre_roll_child(game, c, state, action)
    return dict(action["data"]["princess_child"])


def bind_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    scope = action["data"]["princess_child"]
    value = _direction(game, c, state, scope["direction"])
    if (
        value.child
        or value.completed_event
        or action["actor_id"] != value.actor.entity
        or action.get("parent_id") != value.parent
        or action["data"]["play"] != value.play
        or scope["actor"] != value.actor.model_dump(mode="json")
        or scope["author"] != value.author_controller
    ):
        raise WorkflowError(
            "Bind only the fixed original counterpart child, without changing its controller"
        )
    rules.put(state, value.model_copy(update=dict(child=action["id"], bound_event=event)))


def _bound(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> rules.HighDirection | None:
    scope = action["data"].get("princess_child")
    if scope is None:
        return None
    value = _direction(game, c, state, scope["direction"])
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    if (
        prepared.source_work != value.id
        or prepared.context != value.context
        or prepared.order_id != value.order_id
        or not _prepared_target(value, prepared)
        or scope.get("target") != (value.target.model_dump(mode="json") if value.target else None)
        or scope.get("order_id") != value.order_id
        or value.child != action["id"]
        or action["actor_id"] != value.actor.entity
        or action["data"]["play"] != value.play
        or action.get("parent_id") != value.parent
        or scope["actor"] != value.actor.model_dump(mode="json")
        or scope["author"] != value.author_controller
        or action["data"].get("character_ids", {}).get(value.actor.entity)
        != value.actor.incarnation
    ):
        raise WorkflowError(
            "Keep the real counterpart actor/controller and immutable Princess author"
        )
    return value


def authorize_child(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> ActorRef | None:
    value = _bound(game, c, state, action)
    if value is None:
        return None
    if viewer.user_id != value.author_controller:
        raise WorkflowError("The original Princess exclusively owns this child's actor decisions")
    return value.actor


def child_author(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    value = _bound(game, c, state, action)
    return value.author_controller if value else None


def _performer_row(value: rules.HighDirection, action: dict[str, Any], row: dict[str, Any]) -> bool:
    if row["actor_id"] != value.actor.entity:
        return False
    if row["kind"] == "dose_up_components" and action["data"].get("dose_up", {}).get(
        "princess_direction"
    ):
        return bool(json.loads(row["body_json"]).get("dose_role") == "roller")
    if row["kind"].startswith("npc_flirt_"):
        return bool(action["data"].get("npc_flirt")) and json.loads(row["body_json"]).get(
            "subject"
        ) == value.actor.model_dump(mode="json")
    return True


def decision_author(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> int | None:
    value = _bound(game, c, state, action)
    if value is None or not _performer_row(value, action, row):
        return None
    if value.completed_event and row["state"] == "pending":
        raise WorkflowError("This completed one-child decision grant has expired")
    return value.author_controller


def prove_response_author(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    event: str,
) -> int | None:
    author = decision_author(game, c, state, action, row)
    if author is not None:
        _event(game, c, event, ("m2.choice_resolved", "m3.choice_resolved"), author, action["id"])
        audit = c.scalar(
            sa.select(t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        if json.loads(audit or "{}").get("choice_id") != row["id"]:
            raise WorkflowError(
                "Recover the actual original row answered by its true scoped author"
            )
    return author


def complete_child(
    game: GameService, c: Connection, state: GameState, child: dict[str, Any], event: str
) -> bool:
    value = _bound(game, c, state, child)
    if value is None:
        return False
    if (
        child["state"] != "complete"
        or not child["data"].get("receipt")
        or not child["data"].get("result")
        or game.pending(c, child["id"])
    ):
        raise WorkflowError(
            "Complete the actual original counterpart's rolled child, not an acknowledgment"
        )
    if value.play == "dose_up" and not value.completed_event:
        from girlframe.services.m3_dose_up import validate_pending_controlled_dose

        validate_pending_controlled_dose(game, c, state, child, event)
    if value.completed_event:
        if value.completed_event != event:
            raise WorkflowError("This single child was already completed")
        return True
    rules.put(state, value.model_copy(update=dict(completed_event=event)))
    parent = game.action(c, value.parent)
    for row in game.pending(c, value.parent):
        if row["kind"] != "princess_sex_child" or row["actor_id"] != str(value.author_controller):
            raise WorkflowError(
                "Recover the actual parent child requirement before source completion"
            )
        c.execute(
            t.m2["m2_choices"]
            .update()
            .where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == row["id"],
            )
            .values(
                state="answered",
                revision=row["revision"] + 1,
                body_json=json.dumps(
                    json.loads(row["body_json"])
                    | dict(completed_child=child["id"], completion_event=event)
                ),
            )
        )
    _finish(game, c, state, parent, event)
    return True


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    if action["data"].get("princess_child"):
        value = _bound(game, c, state, action)
        if value is not None and value.completed_event == event:
            parent = game.action(c, value.parent)
            session = prove(game, c, state, value.session)
            if parent["state"] != "complete" or session.completed_event != event:
                raise WorkflowError(
                    "Complete only the actual child and its canonical Princess parent"
                )
            if session.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(game, c, state, session.id, event)
    elif action["data"].get("princess_sex"):
        session = prove(game, c, state, action["data"]["princess_sex"]["session"])
        if session.changeling_source is not None:
            from girlframe.services.m3_changeling_sex import synchronize_session as synchronize_link

            synchronize_link(game, c, state, session.id, event)


class SexService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast, actor = _cast(self.game, c, state, channel), current_ref(state, viewer.user_id)
            from girlframe.services.m3_learned_sex import lessons

            learned = lessons(self.game, c, state, actor, rules.RULE)
            targets = []
            if actor.kind == "pilot" and (
                learned or has_rule(state.sheets[actor.entity], rules.RULE, "PRINCESS")
            ):
                for role in cast.roles:
                    try:
                        _contact(
                            self.game,
                            c,
                            state,
                            actor,
                            role.actor,
                            channel,
                            lesson_id=learned[0]["id"] if learned else None,
                        )
                    except (WorkflowError, ValueError):
                        continue
                    targets.append(
                        dict(
                            ref=role.actor.model_dump(mode="json"),
                            token=role.actor.token,
                            label=resolve(
                                state, role.actor, profiles(c, self.store.campaign_id)
                            ).label,
                        )
                    )
            return dict(
                revision=state.revision,
                lessons=learned,
                targets=targets,
                sessions=[
                    dict(id=x.id, phase=x.phase, caster=x.caster, counterpart=x.counterpart)
                    for x in rules.sessions(state)
                    if viewer.user_id in (x.caster, x.counterpart) and x.cast.channel == channel
                ],
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if viewer.user_id not in (value.caster, value.counterpart):
                raise WorkflowError(
                    "Only the actual original participants may read this private interaction"
                )

            directive = (
                _direction(self.game, c, state, value.direction)
                if value.direction and value.caster == viewer.user_id and value.phase == "child"
                else None
            )
            if directive is not None and directive.child is None:
                _contact(
                    self.game,
                    c,
                    state,
                    value.actor,
                    value.target,
                    value.cast.channel,
                    bonded_source=value.bonded_source,
                    changeling_source=value.changeling_source,
                    learned_source=value.learned_source,
                )
            from girlframe.services.m3_learned_sex import cancelled

            return value.model_dump(mode="json", exclude={"cast", "registry"}) | dict(
                lesson_cancelled=cancelled(self.game, c, state, value.learned_source),
                revision=state.revision,
                child=(
                    child_projection(self.game, c, state, directive.id)
                    if directive is not None
                    else None
                ),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        from girlframe.services.m3_learned_sex import cancelled

        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Princess voluntary source — "
                + ("cancelled" if cancelled(self.game, c, state, x.learned_source) else x.phase),
                phase="cancelled" if cancelled(self.game, c, state, x.learned_source) else x.phase,
                pending=not cancelled(self.game, c, state, x.learned_source)
                and (
                    (x.phase == "invited" and x.counterpart == viewer.user_id)
                    or (x.phase == "accepted" and x.caster == viewer.user_id)
                    or (
                        x.phase == "child"
                        and x.caster == viewer.user_id
                        and x.direction is not None
                        and rules.direction(state, x.direction).child is None
                    )
                ),
            )
            for x in rules.sessions(state)
            if viewer.user_id in (x.caster, x.counterpart)
        ]

    def invite(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        target: ActorRef,
        expected: int,
        account: str,
        *,
        bonded_source: str | None = None,
        changeling_source: str | None = None,
        learned_source: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            _contact(
                self.game,
                c,
                state,
                actor,
                target,
                channel,
                bonded_source=bonded_source,
                changeling_source=changeling_source,
                lesson_id=learned_source,
            )
            if state.revision != expected or self.game.pending_actions(c):
                raise WorkflowError(
                    "Finish pending Plays and use the actual current voluntary source"
                )
            event = str(uuid4())
            assert self.store.policy.m3_approval is not None
            value = rules.Session(
                id=str(uuid4()),
                actor=actor,
                bonded_source=bonded_source,
                changeling_source=changeling_source,
                target=target,
                caster=viewer.user_id,
                counterpart=int(target.entity),
                cast=_cast(self.game, c, state, channel),
                registry=self.store.policy.m3_approval.registry_sha256,
                proposed_event=event,
                proposal=account.strip(),
            )
            if learned_source is not None:
                from girlframe.services.m3_learned_sex import reserve_invitation

                source = reserve_invitation(self.game, c, state, value, rules.RULE, learned_source)
                value = value.model_copy(update=dict(learned_source=source))
            rules.put(state, value)
            if changeling_source is not None:
                from girlframe.services.m3_changeling_sex import bind_source

                bind_source(
                    self.game,
                    c,
                    state,
                    changeling_source,
                    value.id,
                    rules.RULE,
                    value.proposed_event,
                )
            if bonded_source is not None:
                from girlframe.services.m3_bonded import bind_delegation

                bind_delegation(self.game, c, state, bonded_source, value.id, rules.RULE, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.princess_sex_invited",
                state,
                event_id=event,
                session=value.id,
            )
            return dict(id=value.id)

        return self.store._write(
            viewer,
            key,
            "m3.princess_sex_invited",
            dict(
                channel=channel,
                target=target.model_dump(mode="json"),
                expected=expected,
                account=account,
            )
            | ({"bonded_source": bonded_source} if bonded_source is not None else {})
            | ({"changeling_source": changeling_source} if changeling_source is not None else {})
            | ({"learned_source": learned_source} if learned_source is not None else {}),
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
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if (
                state.revision != expected
                or value.phase != "invited"
                or viewer.user_id != value.counterpart
                or type(accept) is not bool
                or not account.strip()
                or self.game.pending_actions(c)
            ):
                raise WorkflowError(
                    "The actual original counterpart owns this disclosed source reply"
                )
            _contact(
                self.game,
                c,
                state,
                value.actor,
                value.target,
                value.cast.channel,
                bonded_source=value.bonded_source,
                changeling_source=value.changeling_source,
                learned_source=value.learned_source,
            )
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        consent_event=event,
                        consent_account=account.strip(),
                        phase="accepted" if accept else "declined",
                    )
                ),
            )
            from girlframe.services.m3_learned_sex import record_consent

            record_consent(self.game, c, state, rules.get(state, value.id), accept, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.princess_sex_consent",
                state,
                event_id=event,
                session=identity,
            )
            if value.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(self.game, c, state, value.id, event)
            return dict(id=identity, accepted=accept)

        return self.store._write(
            viewer,
            key,
            "m3.princess_sex_consent",
            dict(id=identity, expected=expected, accept=accept, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )
