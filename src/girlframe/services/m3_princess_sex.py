"""Real voluntary Princess source, owned outcomes and one actual counterpart child."""

import json
from typing import Any
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
) -> None:
    from girlframe.services.m3_bonded import admit_delegation
    from girlframe.services.m3_changeling_sex import admit_contact

    if changeling_source is not None and bonded_source is not None:
        raise WorkflowError("Keep actual psychic contact separate from Bonded delegation")
    remote = admit_contact(game, c, state, actor, target, rules.RULE, changeling_source)

    if actor.kind != "pilot" or target.kind != "pilot" or actor == target:
        raise WorkflowError("This interaction needs two actual original native Girls")
    bound = profiles(c, game.store.campaign_id)
    own, other = resolve(state, actor, bound), resolve(state, target, bound)
    cast = _cast(game, c, state, channel)
    if (
        cast.adjudicator is not None
        or not (
            has_rule(state.sheets[actor.entity], rules.RULE, "PRINCESS")
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
        _strict(answer, ("keep_your_head",), text=True)
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
            play="keep_your_head",
            context=answer.text.strip(),
        )
        rules.put(state, direction)
        rules.put(state, value.model_copy(update=dict(direction=direction.id, phase="child")))
        game.request(c, action, value.caster, "princess_sex_child", dict(direction=direction.id))
    else:
        raise WorkflowError("Use the exact original Princess source decision")


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = prove(game, c, state, action["data"]["princess_sex"]["session"])
    return dict(
        session=value.id,
        favour=value.favour,
        direction=value.direction,
        plays=[dict(id="keep_your_head", label="Keep Your Head — actual legal action")],
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
                if choice["actor_id"] == value.actor.entity
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
        or prepared.order_id
        or prepared.off_duty_id
        or prepared.target is not None
        or prepared.target_actor is not None
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
        or parent["state"] == "complete"
        or pending is None
    ):
        raise WorkflowError(
            "Only the original Princess directs this fixed counterpart's actual single legal child"
        )
    if prepared.kicked_puppy_basis or prepared.dampener_modifier is not None:
        raise WorkflowError(
            "UNSUPPORTED_RULE: this controlled child needs its actual "
            "Kicked/Dampener source adapter"
        )
    _contact(
        game,
        c,
        state,
        session.actor,
        session.target,
        channel,
        bonded_source=session.bonded_source,
        changeling_source=session.changeling_source,
    )
    return dict(
        direction=value.id,
        session=value.session,
        parent=value.parent,
        actor=value.actor.model_dump(mode="json"),
        actor_controller=value.actor_controller,
        author=value.author_controller,
        choice=pending["id"],
        cast=session.cast.model_dump(mode="json"),
        table=sorted(
            {x.controller for x in session.cast.roles}
            | ({session.cast.facilitator} if session.cast.facilitator else set())
        ),
    )


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
    if (
        value.child != action["id"]
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


def decision_author(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> int | None:
    value = _bound(game, c, state, action)
    if value is None or row["actor_id"] != value.actor.entity:
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
            targets = []
            if actor.kind == "pilot" and has_rule(
                state.sheets[actor.entity], rules.RULE, "PRINCESS"
            ):
                for role in cast.roles:
                    try:
                        _contact(self.game, c, state, actor, role.actor, channel)
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
            from girlframe.services.m3_nightmare import entitlement

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
                )
            return value.model_dump(mode="json", exclude={"cast", "registry"}) | dict(
                revision=state.revision,
                child=(
                    dict(
                        sheet_revision=state.sheets[value.target.entity].revision,
                        heat=state.sheets[value.target.entity].heat,
                        context=directive.context,
                        nightmare=bool(entitlement(self.game, c, state, value.target)),
                        actor=value.target.model_dump(mode="json"),
                        identities=[
                            dict(id=x.id, name=x.name)
                            for x in state.sheets[value.target.entity].identities
                            if not x.marked
                        ],
                    )
                    if directive is not None and directive.child is None
                    else None
                ),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Princess voluntary source — " + x.phase,
                phase=x.phase,
                pending=(x.phase == "invited" and x.counterpart == viewer.user_id)
                or (x.phase == "accepted" and x.caster == viewer.user_id)
                or (
                    x.phase == "child"
                    and x.caster == viewer.user_id
                    and x.direction is not None
                    and rules.direction(state, x.direction).child is None
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
            | ({"changeling_source": changeling_source} if changeling_source is not None else {}),
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
