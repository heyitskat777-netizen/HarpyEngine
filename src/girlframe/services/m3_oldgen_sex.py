"""Voluntary original-body sources and all human-owned Oldgen Sex outcomes."""

from typing import Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_oldgen as maxims
from girlframe.engine import m3_oldgen_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, TagState, shift_status
from girlframe.engine.m3_actor_bonds import change, current_ref, depth, is_helpless
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird import actor_tags, give_tag
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_malleable import _audit
from girlframe.services.m3_oldgen import prove_unmark
from girlframe.services.m3_princess_sex import _event
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("oldgen_sex_effects", "oldgen_sex_creep", "oldgen_sex_rewrite")


def _copy(state: GameState, changed: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(changed, key))


def _record[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in rules.records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original Oldgen Sex consequence")
    return value


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _npc_space(game: GameService, c: Connection, state: GameState, actual: Any) -> None:
    """Reject known incompatibilities; this does not turn unknown occupancy into outside."""
    from girlframe.engine.m3_passengers import passenger_view
    from girlframe.services.m3_changeling_body import _fact

    fact = _fact(game, c, state, actual.ref)
    if (
        fact.kind != "human_npc"
        or fact.vessel != actual.vessel_id
        or actual.inside_frame is True
        or actual.occupied_frame_instance is not None
        or actual.offstage_source
        or actual.custody not in (None, "free")
        or actual.cell is None
        or passenger_view(state, actual.ref) is not None
    ):
        raise WorkflowError(
            "Recover genuine available NPC body/contact; no enclosure or ride proxy"
        )


def _prove_npc_contact(game: GameService, c: Connection, value: rules.Session) -> None:
    contact = value.npc_contact
    if contact is None or (
        contact.session,
        contact.target,
        contact.actor,
        contact.controller,
        contact.vessel,
        contact.actor_vessel,
        contact.cast,
        contact.event,
    ) != (
        value.id,
        value.target,
        value.actor,
        value.counterpart,
        value.target_vessel,
        value.actor_vessel,
        value.cast,
        value.consent_event,
    ):
        raise WorkflowError(
            "Recover the NPC controller's positive invitation-specific contact fact"
        )
    _audit(game, c, contact.event, "m3.oldgen_sex_consent", contact.controller)
    born = _history(c, game, contact.event)
    saved = rules.get(born, value.id)
    if (
        saved.npc_contact != contact
        or saved.phase != "accepted"
        or born.revision != contact.revision + 1
    ):
        raise WorkflowError("Preserve the actual canonical contact statement and revision")
    bindings = snapshot_profiles(c, game.store.campaign_id, born)
    own, other = resolve(born, value.actor, bindings), resolve(born, value.target, bindings)
    _npc_space(game, c, born, other)
    if (
        own.cell != contact.cell
        or other.cell != contact.cell
        or other.controller != contact.controller
        or own.inside_frame is not False
        or own.vessel_id != contact.actor_vessel
        or other.vessel_id != contact.vessel
    ):
        raise WorkflowError("Recover the actual original contact bodies and authored location")


def _counterpart(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Any:
    if actor.kind == "pilot":
        return _native(game, c, state, actor)
    if actor.kind != "npc":
        raise WorkflowError("Use a supported original Pilot or ordinary NPC counterpart")
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        actual.rules != "npc"
        or not actual.alive
        or actual.offstage_source
        or actual.custody not in (None, "free")
        or actual.vessel_id is None
    ):
        raise WorkflowError("Use the actual available ordinary NPC and original body")
    _npc_space(game, c, state, actual)
    return actual


def _contact(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Session,
    *,
    lesson_id: str | None = None,
    pending_event: str | None = None,
    proposing_npc: bool = False,
) -> None:
    from girlframe.services.m3_bonded import admit_delegation
    from girlframe.services.m3_changeling_sex import admit_contact
    from girlframe.services.m3_learned_sex import admit_offer, admit_source

    if (
        sum(
            x is not None
            for x in (value.changeling_source, value.bonded_source, value.learned_source, lesson_id)
        )
        > 1
    ):
        raise WorkflowError("Keep learned, psychic and Bonded sources separate")
    learned = (
        admit_source(
            game,
            c,
            state,
            value.actor,
            value.target,
            rules.RULE,
            value.learned_source,
            pending_event=pending_event,
        )
        if value.learned_source is not None
        else admit_offer(game, c, state, value.actor, rules.RULE, lesson_id)
    )
    remote = admit_contact(
        game, c, state, value.actor, value.target, rules.RULE, value.changeling_source
    )

    own, other = _native(game, c, state, value.actor), _counterpart(game, c, state, value.target)
    cast = _cast(game, c, state, value.cast.channel)
    if value.target.kind == "npc" and not proposing_npc:
        _prove_npc_contact(game, c, value)
        assert value.npc_contact is not None
        if other.cell != value.npc_contact.cell or own.cell != value.npc_contact.cell:
            raise WorkflowError("The original invitation-specific contact no longer holds")
    if (
        value.actor == value.target
        or (value.target.kind == "npc" and any((value.bonded_source, value.changeling_source)))
        or (
            not learned
            and value.bonded_source is None
            and state.sheets[value.actor.entity].girl != "OLDGEN"
        )
        or not (
            (learned or has_rule(state.sheets[value.actor.entity], rules.RULE, "OLDGEN"))
            if value.bonded_source is None
            else admit_delegation(
                game, c, state, value.actor, value.target, rules.RULE, value.bonded_source
            )
        )
        or cast != value.cast
        or (own.controller, other.controller) != (value.caster, value.counterpart)
        or (
            not remote
            and any(
                (x.ref.kind == "pilot" and x.inside_frame is not False) or x.cell is None
                for x in (own, other)
            )
        )
        or (not remote and own.cell != other.cell)
        or (own.vessel_id, other.vessel_id) != (value.actor_vessel, value.target_vessel)
        or any(is_helpless(state, x) for x in (value.actor, value.target))
        or not all(
            any(r.actor == ref and r.controller == human for r in cast.roles)
            for ref, human in ((value.actor, value.caster), (value.target, value.counterpart))
        )
    ):
        raise WorkflowError(
            "Use the actual available original Oldgen and counterpart together outside Frames"
        )


def _birth_contact(
    game: GameService, c: Connection, state: GameState, value: rules.Session
) -> None:
    """The proved canonical invitation saves real bodies/cast; no current SQL scene read."""
    bound = snapshot_profiles(c, game.store.campaign_id, state)
    own, other = resolve(state, value.actor, bound), resolve(state, value.target, bound)
    remote = value.changeling_source is not None
    if value.target.kind == "npc":
        _npc_space(game, c, state, other)
    if (
        value.actor.kind != "pilot"
        or value.target.kind not in ("pilot", "npc")
        or (
            value.target.kind == "npc"
            and (other.rules != "npc" or any((value.bonded_source, value.changeling_source)))
        )
        or value.actor == value.target
        or value.cast not in state.scene_casts
        or not value.cast.open
        or value.cast.adjudicator is not None
        or value.cast.facilitator != state.handler
        or (own.controller, other.controller) != (value.caster, value.counterpart)
        or any(
            (
                x.ref.kind == "pilot"
                and (x.rules != "girl_frame" or state.sheets[x.ref.entity].medical_state != "fit")
            )
            or not x.alive
            or x.offstage_source
            or x.custody not in (None, "free")
            or (
                not remote
                and ((x.ref.kind == "pilot" and x.inside_frame is not False) or x.cell is None)
            )
            for x in (own, other)
        )
        or (not remote and own.cell != other.cell)
        or (own.vessel_id, other.vessel_id) != (value.actor_vessel, value.target_vessel)
        or any(is_helpless(state, x) for x in (value.actor, value.target))
        or (
            value.learned_source is None
            and value.bonded_source is None
            and (
                state.sheets[value.actor.entity].girl != "OLDGEN"
                or not has_rule(state.sheets[value.actor.entity], rules.RULE, "OLDGEN")
            )
        )
        or not all(
            any(x.actor == actor and x.controller == controller for x in value.cast.roles)
            for actor, controller in (
                (value.actor, value.caster),
                (value.target, value.counterpart),
            )
        )
    ):
        raise WorkflowError("Recover the original invitation's actual bodies, cast and authors")


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Session:
    value = rules.get(state, identity)
    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import prove_source_link

        prove_source_link(
            game, c, state, value.changeling_source, value.id, value.actor, value.target, rules.RULE
        )

    if value.learned_source is not None:
        from girlframe.services.m3_learned_sex import prove as prove_lesson

        link = prove_lesson(game, c, state, value.learned_source)
        if (link.rule_id, link.session, link.actor, link.target) != (
            rules.RULE,
            value.id,
            value.actor,
            value.target,
        ):
            raise WorkflowError("Preserve this original learned Oldgen source")
    origin = _history(c, game, value.proposed_event)
    born = rules.get(origin, identity)
    from girlframe.services.m3_bonded import prove_delegation
    from girlframe.services.m3_learned_bonded_oldgen import released_parent

    released_delegation = released_parent(game, c, state, value)
    if not released_delegation:
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
        "actor_vessel",
        "target_vessel",
        "proposed_event",
        "proposal",
        "bonded_source",
        "changeling_source",
        "learned_source",
    )
    _audit(game, c, value.proposed_event, "m3.oldgen_sex_invited", value.caster)
    if any(getattr(value, k) != getattr(born, k) for k in stable):
        raise WorkflowError("Preserve the original people, bodies and voluntary source")
    _birth_contact(game, c, origin, born)
    withdrawn_unused = (
        value.phase == "withdrawn"
        and (
            released_delegation
            or value.learned_source is not None
            and link.released_kind == "withdrawn"
            and link.released_event is not None
        )
        and value.action is None
        and value.bound_event is None
        and value.effect_event is None
    )
    if (
        value.target.kind == "npc"
        and value.phase not in ("invited", "declined")
        and not (withdrawn_unused and value.consent_event is None)
    ):
        _prove_npc_contact(game, c, value)
    if value.phase != "invited" and value.consent_event is None and not withdrawn_unused:
        raise WorkflowError("Recover the actual counterpart's source answer before continuing")
    if value.consent_event:
        saved = rules.get(_history(c, game, value.consent_event), identity)
        _audit(game, c, value.consent_event, "m3.oldgen_sex_consent", value.counterpart)
        if (
            saved.phase not in ("accepted", "declined")
            or saved.consent_account != value.consent_account
            or any(getattr(saved, k) != getattr(value, k) for k in stable)
        ):
            raise WorkflowError(
                "Recover the actual original counterpart's own voluntary source answer"
            )
    if value.bound_event:
        saved = rules.get(_history(c, game, value.bound_event), identity)
        _event(
            game,
            c,
            value.bound_event,
            ("m2.play_confirmed", "m3.play_confirmed"),
            value.caster,
            value.action,
        )
        if (
            saved.action != value.action
            or saved.phase != "active"
            or not value.consent_event
            or rules.get(_history(c, game, value.consent_event), identity).phase != "accepted"
        ):
            raise WorkflowError("Bind only the original genuinely accepted source once")
    if value.effect_event:
        action = game.action(c, value.action or "")
        _, total = _roll_source(game, c, action)
        expected = "low" if total <= 7 else "mid" if total <= 10 else "high"
        saved = rules.get(_history(c, game, value.effect_event), identity)
        if (
            action["data"].get("oldgen_sex", {}).get("session") != identity
            or saved.effect_event != value.effect_event
            or saved.tier != expected
            or value.tier != expected
        ):
            raise WorkflowError("Recover the real original spent-Heat roll and actual result")
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
    assert game.store.policy.m3_approval is not None
    if (
        value.phase != "accepted"
        or value.registry != game.store.policy.m3_approval.registry_sha256
        or value.caster != viewer.user_id
        or prepared.target_actor != value.target
        or channel != value.cast.channel
        or prepared.target is not None
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
    ):
        raise WorkflowError("Use this exact original accepted voluntary Oldgen source")
    _contact(game, c, state, value)
    handler = active_handler(state)
    if handler is None:
        raise WorkflowError("Use the actual original Handler scene context")
    if value.cast.facilitator is None or state.handler is None:
        raise WorkflowError("Recover the genuine source facilitator and Handler before this Play")
    from girlframe.services.m3_learned_bonded_oldgen import parent_lesson

    delegated_lesson = parent_lesson(state, value)
    return (
        dict(
            session=value.id,
            actor=value.actor.model_dump(mode="json"),
            target=value.target.model_dump(mode="json"),
            caster=value.caster,
            counterpart=value.counterpart,
            handler=handler.model_dump(mode="json"),
            handler_controller=state.handler,
            cast=value.cast.model_dump(mode="json"),
            cast_sha256=fingerprint(value.cast),
            table=sorted({x.controller for x in value.cast.roles} | {state.handler}),
        )
        | ({"learned_source": value.learned_source} if value.learned_source is not None else {})
        | ({"bonded_source": value.bonded_source} if value.bonded_source is not None else {})
        | ({"bonded_lesson": delegated_lesson} if delegated_lesson is not None else {})
        | (
            {"changeling_source": value.changeling_source}
            if value.changeling_source is not None
            else {}
        )
    )


def bind(state: GameState, action: dict[str, Any], event: str | None = None) -> None:
    value = rules.get(state, action["data"]["oldgen_sex"]["session"])
    if value.phase != "accepted" or value.action or not event:
        raise WorkflowError("Bind the genuinely accepted original interaction once")
    rules.put(
        state, value.model_copy(update=dict(action=action["id"], bound_event=event, phase="active"))
    )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    value = prove(
        game, c, load_state(c, game.store.campaign_id), action["data"]["oldgen_sex"]["session"]
    )
    if value.target.kind == "npc":
        actual = _counterpart(game, c, load_state(c, game.store.campaign_id), value.target)
        if actual.controller != value.counterpart:
            raise WorkflowError("Recover the original NPC controller before choosing an outcome")
    if value.action != action["id"] or viewer.user_id not in action["data"]["oldgen_sex"]["table"]:
        raise WorkflowError("Only this actual original source table owns these choices")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    value = rules.get(state, action["data"]["oldgen_sex"]["session"])
    if viewer.user_id != value.caster or value.phase != "active" or value.effect_event:
        raise WorkflowError("Roll the original confirmed interaction once")
    _contact(game, c, state, value)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.get(state, action["data"]["oldgen_sex"]["session"])
    if value.effect_event:
        raise WorkflowError("Resume the actual original result without duplicating it")
    from girlframe.services.m3_gender_designation import offer_animal_tags

    if offer_animal_tags(game, c, state, action):
        action["data"]["gender_sex_deferred"] = True
        return
    _, total = _roll_source(game, c, action)
    level = "low" if total <= 7 else "mid" if total <= 10 else "high"
    rules.put(
        state,
        value.model_copy(
            update=dict(
                effect_event=action["data"]["response_event"],
                tier=level,
                phase="rewrite" if level == "low" else "caster",
            )
        ),
    )
    game.request(
        c,
        action,
        value.counterpart if level == "low" else value.caster,
        "oldgen_sex_rewrite" if level == "low" else "oldgen_sex_effects",
    )


def _finish(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    value = rules.get(state, action["data"]["oldgen_sex"]["session"])
    rules.put(
        state,
        value.model_copy(
            update=dict(phase="complete", completed_event=action["data"]["response_event"])
        ),
    )
    ChoiceEngine(game).finish(c, state, action)


def _selection(
    game: GameService, c: Connection, state: GameState, value: rules.Selection
) -> ChoiceAnswer:
    session = prove(game, c, state, value.session)
    kind = (
        "oldgen_sex_creep"
        if value.role == "creep"
        else "oldgen_sex_rewrite"
        if value.role == "rewrite"
        else "oldgen_sex_effects"
    )
    owner = (
        session.counterpart if value.role in ("reciprocal", "creep", "rewrite") else session.caster
    )
    answer = _response(game, c, value.action, value.id, value.event, owner, kind)
    if (
        value.controller != owner
        or value.action != session.action
        or value not in rules.records(_history(c, game, value.event), rules.Selection)
        or value.options != answer.options
        or value.text != answer.text
        or value.maxim != answer.fields.get("maxim")
    ):
        raise WorkflowError("Recover the original actual human's exact owned effect selection")
    return answer


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    value = rules.get(state, action["data"]["oldgen_sex"]["session"])
    role = value.phase
    owner = value.counterpart if role in ("rewrite", "creep", "reciprocal") else value.caster
    if (
        int(row["actor_id"]) != owner
        or answer.denied
        or answer.number is not None
        or answer.flag is not None
        or answer.member is not None
        or set(answer.fields) - {"tag", "maxim"}
    ):
        raise WorkflowError("Supply only your actual owned Oldgen Sex result")
    event = action["data"]["response_event"]
    selected = rules.Selection(
        id=row["id"],
        session=value.id,
        action=action["id"],
        controller=owner,
        role=cast(rules.Role, role),
        options=answer.options,
        text=answer.text,
        maxim=answer.fields.get("maxim"),
        event=event,
    )
    if role == "creep":
        if answer.options not in (("yes",), ("no",)) or answer.fields or answer.text:
            raise WorkflowError(
                "Only the actual counterpart answers whether she thinks Oldgen is a creep"
            )
        rules.put(state, selected)
        yes = answer.options == ("yes",)
        rules.put(
            state,
            value.model_copy(update=dict(creep=yes, phase="reciprocal" if yes else "additional")),
        )
        game.request(c, action, value.counterpart if yes else value.caster, "oldgen_sex_effects")
        return
    if role == "rewrite":
        if answer.options == ("decline",) and not answer.fields and not answer.text:
            rules.put(state, selected)
        elif (
            answer.options == ("rewrite",)
            and set(answer.fields) == {"maxim"}
            and answer.text.strip()
            and len(answer.text) <= 300
        ):
            token = answer.fields["maxim"]
            if not token.startswith("oldgen:"):
                from girlframe.services.m3_oldgen import _maxim

                original = _maxim(game, c, state, token)
                if original.owner != value.actor:
                    raise WorkflowError("Rewrite only this original Oldgen's actual maxim")
            maxims.rewrite_maxim(state, value.caster, token, answer.text.strip(), event)
            rules.put(state, selected)
            rules.put(
                state,
                rules.Effect(
                    id=row["id"] + ":rewrite",
                    session=value.id,
                    action=action["id"],
                    selection=row["id"],
                    owner=value.target,
                    target=value.actor,
                    kind="rewrite",
                    event=event,
                    maxim=token,
                    text=answer.text.strip(),
                ),
            )
        else:
            raise WorkflowError(
                "The original counterpart may rewrite one actual owned maxim or decline"
            )
        _finish(game, c, state, action)
        return
    if role not in ("caster", "reciprocal", "additional"):
        raise WorkflowError("Resume the actual original effect phase")
    count = 2 if role == "caster" else 1
    used = {
        x.kind
        for x in rules.records(state, rules.Effect)
        if x.session == value.id and x.owner == value.actor
    }
    allowed = set(rules.EFFECTS) - (used if role == "additional" else set())
    if (
        not (count if role == "caster" else 0) <= len(answer.options) <= count
        or len(set(answer.options)) != len(answer.options)
        or not set(answer.options) <= allowed
        or bool(answer.fields.get("tag", "").strip()) != ("tag" in answer.options)
        or bool(answer.fields.get("maxim")) != ("unmark" in answer.options)
        or answer.text
    ):
        raise WorkflowError("Choose the exact distinct printed effects and their necessary fields")
    chooser, target = (
        (value.target, value.actor) if role == "reciprocal" else (value.actor, value.target)
    )
    for kind in answer.options:
        fields: dict[str, Any] = {}
        if kind == "tag":
            tag_id = "oldgen-sex-tag:" + row["id"]
            _copy(
                state,
                give_tag(
                    state,
                    profiles(c, game.store.campaign_id),
                    target,
                    chooser,
                    answer.fields["tag"].strip(),
                    tag_id,
                    event,
                    tuple(
                        sorted(
                            {x.controller for x in value.cast.roles}
                            | (
                                {value.cast.facilitator}
                                if value.cast.facilitator is not None
                                else set()
                            )
                        )
                    ),
                ),
            )
            tag = next(x for x in actor_tags(state, target) if x.id == tag_id)
            if target.kind == "npc":
                if not isinstance(tag, WorldTag):
                    raise WorkflowError("Recover the actual NPC WorldTag")
                fields["npc_tag"] = tag
            else:
                if not isinstance(tag, TagState):
                    raise WorkflowError("Recover the actual Pilot Tag")
                tag.giver_character = chooser.incarnation
                fields["tag"] = tag
        elif kind == "status":
            if target.kind != "pilot" or int(target.entity) not in state.order:
                raise WorkflowError(
                    "UNSUPPORTED_NPC_STATUS: pause for human-facilitator adjudication; "
                    "this effect is not resolved and no rank is fabricated."
                )
            fields["before"] = state.order.index(int(target.entity))
            shift_status(state, int(target.entity), -1)
            fields["after"] = state.order.index(int(target.entity))
        elif kind == "unmark":
            token = answer.fields["maxim"]
            prove_unmark(game, c, state, value.caster, token)
            maxims.unmark_maxim(state, value.caster, token)
            fields["maxim"] = token
        elif kind == "bond":
            fields["before"] = depth(state, chooser, target)
            _copy(state, change(state, chooser, target, 1, event))
            fields["after"] = depth(state, chooser, target)
        rules.put(
            state,
            rules.Effect(
                id=row["id"] + ":" + kind,
                session=value.id,
                action=action["id"],
                selection=row["id"],
                owner=chooser,
                target=target,
                kind=cast(rules.EffectKind, kind),
                event=event,
                **fields,
            ),
        )
    rules.put(state, selected)
    if role == "caster" and value.tier == "high":
        rules.put(state, value.model_copy(update=dict(phase="creep")))
        game.request(c, action, value.counterpart, "oldgen_sex_creep")
    else:
        _finish(game, c, state, action)


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = prove(game, c, state, action["data"]["oldgen_sex"]["session"])
    labels = {
        "tag": "Give an actual Tag",
        "status": "Lower actual Status",
        "unmark": "Unmark an actual Oldgen maxim",
        "bond": "Deepen your actual Bond",
        "helpless": "Leave them physiologically unable to act",
    }
    used = {
        x.kind
        for x in rules.records(state, rules.Effect)
        if x.session == value.id and x.owner == value.actor
    }
    marked = maxims.marked_maxims(state, value.caster)
    unsupported_status = value.target.kind == "npc" and value.phase != "reciprocal"
    if unsupported_status:
        labels["status"] = "NPC Status: unsupported; pause for facilitator"
    allowed = [
        x
        for x in rules.EFFECTS
        if (value.phase != "additional" or x not in used) and (x != "unmark" or marked)
    ]
    return dict(
        phase=value.phase,
        unsupported_status=unsupported_status,
        options=tuple((x, labels[x]) for x in allowed),
        minimum=2 if value.phase == "caster" else 0,
        maximum=2 if value.phase == "caster" else 1,
        maxims=marked if value.phase in ("caster", "additional", "reciprocal") else (),
        rewrite=maxims.rewritable_maxims(state, value.caster) if value.phase == "rewrite" else (),
    )


def prove_effect(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Effect:
    value = _record(state, rules.Effect, identity)
    selected = _record(state, rules.Selection, value.selection)
    answer = _selection(game, c, state, selected)
    born = _history(c, game, value.event)
    session = prove(game, c, state, value.session)
    chooser, target = (
        (session.target, session.actor)
        if selected.role == "reciprocal"
        else (session.actor, session.target)
    )
    if value.kind == "rewrite":
        chooser, target = session.target, session.actor
    if (
        value not in rules.records(born, rules.Effect)
        or value.event != selected.event
        or value.owner != chooser
        or value.target != target
        or value.kind not in selected.options
    ):
        raise WorkflowError(
            "Recover the genuine original selected effect and exact original people"
        )
    if value.kind == "tag":
        stored = value.npc_tag if target.kind == "npc" else value.tag
        tag = next((x for x in actor_tags(born, target) if stored and x.id == stored.id), None)
        if (
            tag is None
            or stored is None
            or tag != stored
            or tag.id != "oldgen-sex-tag:" + selected.id
            or tag.label != answer.fields["tag"].strip()
            or (
                target.kind == "npc"
                and (
                    value.tag is not None
                    or not isinstance(tag, WorldTag)
                    or ActorRef.model_validate_json(tag.giver_entity) != chooser
                )
            )
            or (
                target.kind != "npc"
                and (
                    value.npc_tag is not None
                    or not isinstance(tag, TagState)
                    or tag.giver_actor != chooser
                    or tag.giver_character != chooser.incarnation
                )
            )
        ):
            raise WorkflowError("Recover the actual original authored Tag")
    if value.kind in ("unmark", "rewrite") and value.maxim != answer.fields.get("maxim"):
        raise WorkflowError("Recover the actual selected Oldgen maxim")
    return value


def prove_maxim_rewrite(
    game: GameService,
    c: Connection,
    state: GameState,
    owner: int,
    token: str,
    text: str,
    event: str,
) -> None:
    value = next(
        (
            x
            for x in rules.records(state, rules.Effect)
            if x.kind == "rewrite"
            and x.event == event
            and x.target.entity == str(owner)
            and x.maxim == token
            and x.text == text
        ),
        None,
    )
    if value is None:
        raise WorkflowError("Recover the genuine original counterpart's low maxim rewrite")
    prove_effect(game, c, state, value.id)


def recover_helpless(
    game: GameService, c: Connection, state: GameState, subject: ActorRef, event: str
) -> bool:
    changed = False
    for value in rules.records(state, rules.Effect):
        if (
            value.kind == "helpless"
            and value.target == subject
            and not any(x.effect == value.id for x in rules.records(state, rules.Recovery))
        ):
            prove_effect(game, c, state, value.id)
            rules.put(
                state,
                rules.Recovery(
                    id=value.id + ":recovery", effect=value.id, subject=subject, event=event
                ),
            )
            changed = True
    return changed


class OldgenSexService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

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
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe only your actual voluntary interaction")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected or self.game.pending_actions(c):
                raise WorkflowError("Finish pending Plays and reopen the actual source")
            actor = current_ref(state, viewer.user_id)
            own, other = (
                _native(self.game, c, state, actor),
                _counterpart(self.game, c, state, target),
            )
            cast = _cast(self.game, c, state, channel)
            if own.vessel_id is None or other.vessel_id is None:
                raise WorkflowError("Establish the actual original bodies")
            assert self.store.policy.m3_approval is not None
            value = rules.Session(
                id=str(uuid4()),
                actor=actor,
                bonded_source=bonded_source,
                changeling_source=changeling_source,
                target=target,
                caster=viewer.user_id,
                counterpart=other.controller,
                cast=cast,
                registry=self.store.policy.m3_approval.registry_sha256,
                actor_vessel=own.vessel_id,
                target_vessel=other.vessel_id,
                proposed_event=str(uuid4()),
                proposal=account,
            )
            _contact(self.game, c, state, value, lesson_id=learned_source, proposing_npc=True)
            if learned_source is not None:
                from girlframe.services.m3_learned_sex import reserve_invitation

                source = reserve_invitation(self.game, c, state, value, rules.RULE, learned_source)
                value = value.model_copy(update=dict(learned_source=source))
            if cast not in state.scene_casts:
                state.scene_casts.append(cast)
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

                bind_delegation(
                    self.game, c, state, bonded_source, value.id, rules.RULE, value.proposed_event
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.oldgen_sex_invited",
                state,
                event_id=value.proposed_event,
                session=value.id,
            )
            return dict(id=value.id)

        return self.store._write(
            viewer,
            key,
            "m3.oldgen_sex_invited",
            dict(
                channel=channel,
                target=target.model_dump(mode="json"),
                expected=expected,
                account=account,
            )
            | ({"learned_source": learned_source} if learned_source is not None else {})
            | ({"bonded_source": bonded_source} if bonded_source is not None else {})
            | ({"changeling_source": changeling_source} if changeling_source is not None else {}),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def withdraw(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        """Owner-only unused reservation release; never a fictional refusal."""

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            from girlframe.engine import m3_bonded as bonded

            delegated = (
                value.bonded_source is not None
                and bonded.get(state, value.bonded_source).changeling_source is None
            )
            if (
                state.revision != expected
                or viewer.user_id != value.caster
                or current_ref(state, viewer.user_id) != value.actor
                or (value.learned_source is None and not delegated)
                or (value.bonded_source is not None and not delegated)
                or value.changeling_source is not None
                or value.phase not in ("invited", "accepted")
                or value.action is not None
                or value.effect_event is not None
                or value.bound_event is not None
                or value.completed_event is not None
            ):
                raise WorkflowError("Only the original owner may withdraw this unbound invitation")
            actions = t.m2["m2_actions"]
            if c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    sa.or_(
                        sa.func.json_extract(actions.c.body_json, "$.oldgen_sex.session")
                        == identity,
                        sa.func.json_extract(actions.c.body_json, "$.prepared.source_work")
                        == identity,
                    ),
                )
            ):
                raise WorkflowError(
                    "Recover the actual original Action; never refund dice or costs"
                )
            from girlframe.services.m3_learned_sex import withdraw_invitation

            event = str(uuid4())
            if not delegated:
                withdraw_invitation(self.game, c, state, value, event)
            rules.put(state, value.model_copy(update={"phase": "withdrawn"}))
            if delegated:
                from girlframe.services.m3_learned_bonded_oldgen import release

                release(self.game, c, state, identity, viewer.user_id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.oldgen_sex_withdrawn",
                state,
                event_id=event,
                session=identity,
            )
            return dict(id=identity, phase="withdrawn")

        return self.store._write(
            viewer,
            key,
            "m3.oldgen_sex_withdrawn",
            dict(id=identity, expected=expected),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        accept: bool,
        account: str,
        *,
        npc_contact_account: str | None = None,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Record only your own actual source answer")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or value.phase != "invited"
                or viewer.user_id != value.counterpart
            ):
                raise WorkflowError("Answer only your own original current invitation")
            _contact(self.game, c, state, value, proposing_npc=True)
            event = str(uuid4())
            contact = None
            if value.target.kind == "npc" and accept:
                if (
                    not npc_contact_account
                    or not npc_contact_account.strip()
                    or len(npc_contact_account) > 1200
                ):
                    raise WorkflowError(
                        "Attest actual physical contact outside enclosures for this invitation"
                    )
                other = _counterpart(self.game, c, state, value.target)
                assert other.cell is not None
                contact = rules.NpcContact(
                    session=value.id,
                    actor=value.actor,
                    target=value.target,
                    controller=viewer.user_id,
                    vessel=value.target_vessel,
                    actor_vessel=value.actor_vessel,
                    cell=other.cell,
                    cast=value.cast,
                    revision=state.revision,
                    event=event,
                    account=npc_contact_account.strip(),
                )
            elif npc_contact_account is not None:
                raise WorkflowError(
                    "Only an accepting original NPC controller records this contact"
                )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        npc_contact=contact,
                        consent_event=event,
                        consent_account=account,
                        phase="accepted" if accept else "declined",
                    )
                ),
            )
            from girlframe.services.m3_learned_sex import record_consent

            record_consent(self.game, c, state, rules.get(state, identity), accept, event)
            if not accept and value.bonded_source is not None:
                from girlframe.engine import m3_bonded as bonded
                from girlframe.services.m3_learned_bonded_oldgen import release

                if bonded.get(state, value.bonded_source).changeling_source is None:
                    release(self.game, c, state, identity, viewer.user_id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.oldgen_sex_consent",
                state,
                event_id=event,
                session=identity,
            )
            if value.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(self.game, c, state, value.id, event)
            return dict(id=identity, phase="accepted" if accept else "declined")

        return self.store._write(
            viewer,
            key,
            "m3.oldgen_sex_consent",
            dict(
                id=identity,
                expected=expected,
                accept=accept,
                account=account,
                npc_contact_account=npc_contact_account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        from girlframe.services.m3_learned_bonded_oldgen import parent_lesson
        from girlframe.services.m3_learned_sex import cancelled

        return [
            dict(
                id=x.id,
                label="Your actual Oldgen intimacy source",
                revision=state.revision,
                pending=not cancelled(
                    self.game, c, state, x.learned_source or parent_lesson(state, x)
                )
                and (
                    x.phase == "invited"
                    and viewer.user_id == x.counterpart
                    or x.phase == "accepted"
                    and viewer.user_id == x.caster
                ),
            )
            for x in rules.records(state, rules.Session)
            if viewer.user_id in (x.caster, x.counterpart)
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if viewer.user_id not in (value.caster, value.counterpart):
                raise WorkflowError(
                    "Only the original actual participants read this private source"
                )
            effects = [
                prove_effect(self.game, c, state, x.id)
                for x in rules.records(state, rules.Effect)
                if x.session == identity
            ]
            from girlframe.services.m3_learned_bonded_oldgen import parent_lesson
            from girlframe.services.m3_learned_sex import cancelled

            return value.model_dump(mode="json", exclude={"cast", "registry"}) | dict(
                phase="cancelled"
                if cancelled(
                    self.game, c, state, value.learned_source or parent_lesson(state, value)
                )
                else value.phase,
                revision=state.revision,
                effects=[
                    dict(
                        kind=x.kind,
                        target=x.target.model_dump(mode="json"),
                        tag=x.tag.label if x.tag else x.npc_tag.label if x.npc_tag else None,
                    )
                    for x in effects
                ],
            )

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            targets = []
            offered: tuple[dict[str, str], ...] = ()
            from girlframe.engine import m3_bonded as bonded
            from girlframe.services.m3_learned_bonded_oldgen import parent_lesson
            from girlframe.services.m3_learned_sex import cancelled, lessons

            try:
                actor = current_ref(state, viewer.user_id)
                own = _native(self.game, c, state, actor)
                cast = _cast(self.game, c, state, channel)
                offered = lessons(self.game, c, state, actor, rules.RULE)
                if (
                    (
                        state.sheets[actor.entity].girl == "OLDGEN"
                        and has_rule(state.sheets[actor.entity], rules.RULE, "OLDGEN")
                    )
                    or offered
                ) and own.inside_frame is False:
                    for role in cast.roles:
                        if role.actor.kind not in ("pilot", "npc") or role.actor == actor:
                            continue
                        try:
                            other = _counterpart(self.game, c, state, role.actor)
                        except (ValueError, WorkflowError):
                            continue
                        if (
                            (role.actor.kind == "npc" or other.inside_frame is False)
                            and own.cell is not None
                            and own.cell == other.cell
                        ):
                            targets.append(
                                dict(
                                    ref=role.actor.model_dump(mode="json"),
                                    token=role.actor.token,
                                    label=other.label,
                                )
                            )
            except (ValueError, WorkflowError):
                pass
            return dict(
                revision=state.revision,
                targets=targets,
                lessons=offered,
                sessions=[
                    dict(
                        id=x.id,
                        phase="cancelled"
                        if cancelled(
                            self.game, c, state, x.learned_source or parent_lesson(state, x)
                        )
                        else x.phase,
                        can_withdraw=(
                            x.learned_source is not None
                            or x.bonded_source is not None
                            and bonded.get(state, x.bonded_source).changeling_source is None
                        )
                        and x.caster == viewer.user_id
                        and x.action is None
                        and x.phase in ("invited", "accepted"),
                    )
                    for x in rules.records(state, rules.Session)
                    if viewer.user_id in (x.caster, x.counterpart)
                ],
            )
