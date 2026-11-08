"""Real Vatgrown source choices, Investor scenes and bounded learned abilities."""

import json
from collections.abc import Callable
from typing import Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_vatgrown_plays as rules
from girlframe.engine.creation_details import DESIRES
from girlframe.engine.m2 import ChoiceAnswer, GameState, IdentityState, PlayInput
from girlframe.engine.m3_actor_bonds import change, current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_identity_slots import replacement_slot
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_princess_sex import _event
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "vat_sex_learn",
    "vat_sex_plans",
    "vat_sex_good",
    "vat_sex_question",
    "vat_sex_answer",
    "vat_sex_judge",
    "vat_sex_depart",
)


def _copy(state: GameState, changed: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(changed, key))


def _get[T: Model](state: GameState, model: type[T], identity: str) -> T:
    try:
        return rules.find(state, model, identity)
    except ValueError as error:
        raise WorkflowError(str(error)) from None


def _access(game: GameService, c: Connection, viewer: GuildViewer, rule: str = rules.SEX) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rule)


def _vatgrown(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, rule: str
) -> Any:
    actual = _native(game, c, state, actor)
    sheet = state.sheets[actor.entity]
    if sheet.girl != "VATGROWN" or not has_rule(sheet, rule, "VATGROWN"):
        raise WorkflowError("Use this actual original Vatgrown's owned source rule")
    return actual


def _contact(game: GameService, c: Connection, state: GameState, value: rules.Session) -> None:
    from girlframe.services.m3_bonded import admit_delegation
    from girlframe.services.m3_changeling_sex import admit_contact

    if value.changeling_source is not None and value.bonded_source is not None:
        raise WorkflowError("Keep actual psychic contact separate from Bonded delegation")
    remote = admit_contact(
        game, c, state, value.actor, value.target, rules.SEX, value.changeling_source
    )

    own = (
        _vatgrown(game, c, state, value.actor, rules.SEX)
        if value.bonded_source is None
        else _native(game, c, state, value.actor)
    )
    if value.bonded_source is not None:
        admit_delegation(game, c, state, value.actor, value.target, rules.SEX, value.bonded_source)
    other = resolve(
        state, value.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if value.target.kind == "pilot":
        _native(game, c, state, value.target)
    elif value.target.kind not in ("npc", "handler"):
        raise WorkflowError("UNSUPPORTED_VATGROWN_COUNTERPART: use a real supported original body")
    scene = _cast(game, c, state, value.cast.channel)
    if (
        value.actor == value.target
        or scene != value.cast
        or own.controller != value.caster
        or other.controller != value.counterpart
        or not other.alive
        or any(
            (not remote and x.inside_frame is not False)
            or x.offstage_source
            or (not remote and x.cell is None)
            or x.vessel_id is None
            or x.custody not in (None, "free")
            for x in (own, other)
        )
        or (not remote and own.cell != other.cell)
        or (own.vessel_id, other.vessel_id) != (value.actor_vessel, value.target_vessel)
        or is_helpless(state, value.actor)
        or is_helpless(state, value.target)
        or not all(
            any(r.actor == ref and r.controller == owner for r in value.cast.roles)
            for ref, owner in ((value.actor, value.caster), (value.target, value.counterpart))
        )
    ):
        raise WorkflowError(
            "Use the actual available original bodies together with their real source confirmations"
        )


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Session:
    value = _get(state, rules.Session, identity)
    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import prove_source_link

        prove_source_link(
            game, c, state, value.changeling_source, value.id, value.actor, value.target, rules.SEX
        )

    from girlframe.services.m3_bonded import prove_delegation

    if value.bonded_source is not None:
        prove_delegation(
            game, c, state, value.bonded_source, value.id, value.actor, value.target, rules.SEX
        )
    born = _get(_history(c, game, value.proposed_event), rules.Session, identity)
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
    )
    _event(game, c, value.proposed_event, ("m3.vatgrown_sex_invited",), value.caster)
    if any(getattr(value, x) != getattr(born, x) for x in stable):
        raise WorkflowError("Preserve the real original Vatgrown source, bodies and authors")
    _contact(game, c, _history(c, game, value.proposed_event), born)
    if value.consent_event:
        agreed = _get(_history(c, game, value.consent_event), rules.Session, identity)
        _event(game, c, value.consent_event, ("m3.vatgrown_sex_consent",), value.counterpart)
        if (
            agreed.phase not in ("accepted", "declined")
            or agreed.consent_account != value.consent_account
            or any(getattr(agreed, x) != getattr(value, x) for x in stable)
        ):
            raise WorkflowError("Recover the original counterpart's actual voluntary response")
    elif value.phase != "invited":
        raise WorkflowError("The actual original counterpart must answer the source")
    if value.bound_event:
        saved = _get(_history(c, game, value.bound_event), rules.Session, identity)
        _event(
            game,
            c,
            value.bound_event,
            ("m2.play_confirmed", "m3.play_confirmed"),
            value.caster,
            value.action,
        )
        if saved.action != value.action or saved.phase != "active" or not value.consent_event:
            raise WorkflowError("Bind only the actually accepted source")
    if value.effect_event:
        action = game.action(c, value.action or "")
        _, total = _roll_source(game, c, action)
        if action["data"].get("vatgrown_sex", {}).get("session") != value.id or value.tier != (
            "low" if total <= 7 else "mid" if total <= 10 else "high"
        ):
            raise WorkflowError("Recover the genuine source's actual Heat roll and result")
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
        value.caster != viewer.user_id
        or value.phase != "accepted"
        or value.action
        or channel != value.cast.channel
        or prepared.parent
        or prepared.off_duty_id
        or prepared.order_id
        or prepared.target is not None
        or prepared.target_actor is not None
    ):
        raise WorkflowError("Roll only your actual accepted original Vatgrown source")
    _contact(game, c, state, value)
    handler = active_handler(state)
    if handler is None:
        raise WorkflowError("Recover the actual current Handler body")
    if value.cast.facilitator is None or state.handler is None:
        raise WorkflowError("Recover the genuine source facilitator and Handler before this Play")
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
        | ({"bonded_source": value.bonded_source} if value.bonded_source is not None else {})
        | (
            {"changeling_source": value.changeling_source}
            if value.changeling_source is not None
            else {}
        )
    )


def bind(state: GameState, action: dict[str, Any], event: str | None = None) -> None:
    value = rules.get(state, action["data"]["vatgrown_sex"]["session"])
    if value.phase != "accepted" or value.action or not event:
        raise WorkflowError("Bind this genuine accepted source once")
    rules.put(
        state, value.model_copy(update=dict(action=action["id"], bound_event=event, phase="active"))
    )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    prove(game, c, load_state(c, game.store.campaign_id), action["data"]["vatgrown_sex"]["session"])
    if viewer.user_id not in action["data"]["vatgrown_sex"]["table"]:
        raise WorkflowError("Only this actual original table owns source action responses")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    value = prove(game, c, state, action["data"]["vatgrown_sex"]["session"])
    if value.caster != viewer.user_id or value.phase != "active" or value.effect_event:
        raise WorkflowError("Resume the actual source without duplicate Heat or dice")
    _contact(game, c, state, value)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.get(state, action["data"]["vatgrown_sex"]["session"])
    if value.effect_event:
        raise WorkflowError("Resume the original source result without repeating it")
    from girlframe.services.m3_gender_designation import offer_animal_tags

    if offer_animal_tags(game, c, state, action):
        action["data"]["gender_sex_deferred"] = True
        return
    _, total = _roll_source(game, c, action)
    level = "low" if total <= 7 else "mid" if total <= 10 else "high"
    event = action["data"]["response_event"]
    rules.put(
        state,
        value.model_copy(
            update=dict(
                effect_event=event, tier=level, phase="question" if level == "low" else "learning"
            )
        ),
    )
    violation = next(
        (
            x
            for x in rules.records(state, rules.Violation)
            if x.id == rules.identity("sex-attempt", value.id)
        ),
        None,
    )
    if violation:
        rules.put(state, violation.model_copy(update=dict(performed_event=event)))
    if level == "high":
        rules.put(
            state,
            rules.SideCondition(
                id=rules.identity("side", value.id),
                session=value.id,
                actor=value.actor,
                counterpart=value.target,
                event=event,
            ),
        )
    game.request(
        c,
        action,
        value.counterpart if level in ("low", "high") else value.caster,
        "vat_sex_question" if level == "low" else "vat_sex_learn",
    )


def _finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    if game.pending(c, action["id"]):
        return
    value = rules.get(state, action["data"]["vatgrown_sex"]["session"])
    if value.discipline and not _get(state, rules.Discipline, value.discipline).completed_event:
        return
    if value.tier == "low" and not value.departed_event:
        return
    from girlframe.services.m2_choices import ChoiceEngine

    rules.put(state, value.model_copy(update=dict(phase="complete", completed_event=event)))
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def _copy_identities(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Session,
    selection: rules.Selection,
) -> None:
    fields = selection.fields
    teacher = state.sheets.get(value.target.entity) if value.target.kind == "pilot" else None
    selected = tuple(x for x in fields.get("identities", "").split(",") if x)
    replacements = tuple(x for x in fields.get("replacements", "").split(",") if x)
    if teacher is not None:
        if not 1 <= len(selected) <= 2 or len(set(selected)) != len(selected):
            raise WorkflowError("Copy one or two actual distinct counterpart Identities")
        originals = [
            next((x for x in teacher.identities if x.id == identity), None) for identity in selected
        ]
        if any(x is None for x in originals):
            raise WorkflowError("Choose the actual counterpart's existing Identities")
        copied: list[tuple[str | None, str]] = [(x.id, x.name) for x in originals if x is not None]
        if fields.get("identity"):
            raise WorkflowError("This counterpart has real Identities; do not invent substitutes")
    else:
        if selected or not fields.get("identity", "").strip() or len(fields["identity"]) > 120:
            raise WorkflowError(
                "Write one Identity that actually matches this identity-less counterpart"
            )
        copied = [(None, fields["identity"].strip())]
    sheet = state.sheets[value.actor.entity]
    ordinary = [x for x in sheet.identities if not x.protected or x.paired or x.am_limiter]
    needed = max(0, len(ordinary) + len(copied) - 4)
    if len(replacements) != needed or len(set(replacements)) != len(replacements):
        raise WorkflowError(
            "Choose exactly the required actual ordinary Identity replacement slots"
        )
    from girlframe.engine.m3_leviathan_obsession import require_unlocked

    require_unlocked(sheet.identities, replacements)
    if any(
        not any(x.id == identity and not x.protected for x in sheet.identities)
        for identity in replacements
    ):
        raise WorkflowError("Preserve protected, Paired and AM Identity slots")
    if len({text.casefold() for _, text in copied}) != len(copied) or any(
        x.name.casefold() == text.casefold()
        for x in sheet.identities
        if x.id not in replacements
        for _, text in copied
    ):
        raise WorkflowError("Duplicate Identity labels need an explicit source adapter")
    for index, (original, text) in enumerate(copied):
        replaced = replacements[index] if index < len(replacements) else None
        old = next((x for x in sheet.identities if x.id == replaced), None)
        identity = rules.identity("copied-identity", selection.id, str(index))
        locked = bool(old and old.id in sheet.sedation_locked)
        slot = old.slot if old else replacement_slot(sheet, None)
        if old:
            sheet.identities = [x for x in sheet.identities if x.id != old.id]
            sheet.sedation_locked = tuple(
                identity if x == old.id else x for x in sheet.sedation_locked
            )
        sheet.identities.append(IdentityState(id=identity, name=text, marked=locked, slot=slot))
        rules.put(
            state,
            rules.IdentityCopy(
                id=identity,
                actor=value.actor,
                teacher=value.target,
                session=value.id,
                selection=selection.id,
                original=original,
                text=text,
                replaced=replaced,
                event=selection.event,
            ),
        )
    sheet.revision += 1


def _discipline(
    game: GameService,
    c: Connection,
    state: GameState,
    *,
    actor: ActorRef,
    chooser: ActorRef,
    source: str,
    event: str,
    action: str | None,
) -> str:
    from girlframe.services.m3_role_punishments import open_case

    controller = resolve(
        state, chooser, profiles(c, game.store.campaign_id), require_current_profile=False
    ).controller
    identity = rules.identity("discipline", source)
    case = "vatgrown-discipline:" + identity
    value = rules.Discipline(
        id=identity,
        actor=actor,
        chooser=chooser,
        controller=controller,
        event=event,
        source=source,
        case=case,
    )
    rules.put(state, value)
    changed, _ = open_case(
        state,
        profiles(c, game.store.campaign_id),
        actor=chooser,
        target=actor,
        chooser=chooser,
        source_kind="vatgrown_plays",
        action=action,
        source_event=event,
        identity=case,
        source_work=identity,
    )
    _copy(state, changed)
    return identity


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    value = rules.get(state, action["data"]["vatgrown_sex"]["session"])
    event, kind = action["data"]["response_event"], row["kind"]
    if (
        not answer.text.strip()
        or len(answer.text) > 1200
        or answer.number is not None
        or answer.member is not None
        or answer.denied
    ):
        raise WorkflowError(
            "Record your actual owned source choice, without fabricated counterpart answers"
        )
    if kind == "vat_sex_learn":
        expected = 2 if value.tier in ("mid", "high") else 1
        if (
            len(answer.options) != expected
            or len(set(answer.options)) != expected
            or not set(answer.options) <= set(rules.EFFECTS)
            or answer.flag is not None
            or (value.tier == "high" and answer.options != ("identity", "play"))
        ):
            raise WorkflowError(
                "Choose exactly the printed learning effects under the original author's authority"
            )
        if value.learning_event or (
            value.tier == "low"
            and (
                not value.departed_event
                or value.discipline
                and not _get(state, rules.Discipline, value.discipline).completed_event
            )
        ):
            raise WorkflowError(
                "Complete the actual departure and any real Punishment before learning once"
            )
        if set(answer.fields) - {"identities", "identity", "replacements", "play", "plans", "good"}:
            raise WorkflowError("Choose only the actual source learning data")
        selection = rules.Selection(
            id=row["id"],
            session=value.id,
            action=action["id"],
            controller=int(row["actor_id"]),
            choice=row["id"],
            options=answer.options,
            fields=answer.fields,
            account=answer.text.strip(),
            event=event,
        )
        rules.put(state, selection)
        if "identity" in answer.options:
            _copy_identities(game, c, state, value, selection)
        elif any(answer.fields.get(x) for x in ("identities", "identity", "replacements")):
            raise WorkflowError("Identity data requires its actual selected source effect")
        if "play" in answer.options:
            from girlframe.services.m3_learned_plays import SUPPORTED, grant

            rule_id = answer.fields.get("play", "")
            teacher = (
                state.sheets.get(value.target.entity) if value.target.kind == "pilot" else None
            )
            if (
                rule_id not in SUPPORTED
                or teacher is None
                or teacher.girl != SUPPORTED[rule_id][1]
                or not has_rule(teacher, rule_id, SUPPORTED[rule_id][1])
            ):
                raise WorkflowError(
                    "UNSUPPORTED_LEARNED_PLAY: select this original teacher's supported actual Play"
                )
            identity = grant(game, c, state, value.actor, value.target, value.id, rule_id, event)
            rules.put(
                state,
                rules.LearnedPlay(
                    id=identity,
                    actor=value.actor,
                    teacher=value.target,
                    session=value.id,
                    rule_id=rule_id,
                    event=event,
                ),
            )
        elif answer.fields.get("play"):
            raise WorkflowError("Learning a Play requires its actual selected source effect")
        for effect in ("plans", "good"):
            if effect in answer.options:
                if not answer.fields.get(effect, "").strip():
                    raise WorkflowError("Address your actual question to the original counterpart")
                game.request(
                    c,
                    action,
                    value.counterpart,
                    "vat_sex_" + effect,
                    dict(question=answer.fields[effect].strip(), selection=selection.id),
                )
            elif answer.fields.get(effect):
                raise WorkflowError("Only selected source questions may be asked")
        rules.put(state, value.model_copy(update=dict(learning_event=event, phase="answers")))
    elif kind in ("vat_sex_plans", "vat_sex_good"):
        if answer.options or answer.fields or answer.flag is not None:
            raise WorkflowError("The actual counterpart answers the actual addressed question")
        if kind == "vat_sex_good":
            _copy(state, change(state, value.actor, value.target, 1, event))
    elif kind == "vat_sex_question":
        if (
            value.tier != "low"
            or value.question_event
            or answer.options
            or answer.fields
            or answer.flag is not None
        ):
            raise WorkflowError("Ask your own actual question once")
        rules.put(
            state,
            value.model_copy(
                update=dict(question=answer.text.strip(), question_event=event, phase="answer")
            ),
        )
        game.request(c, action, value.caster, "vat_sex_answer", dict(question=answer.text.strip()))
    elif kind == "vat_sex_answer":
        if (
            not value.question_event
            or value.answer_event
            or answer.options
            or answer.fields
            or answer.flag is not None
        ):
            raise WorkflowError("The original Vatgrown gives their own honest fictional answer")
        rules.put(
            state,
            value.model_copy(
                update=dict(answer=answer.text.strip(), answer_event=event, phase="judgment")
            ),
        )
        game.request(c, action, value.counterpart, "vat_sex_judge")
    elif kind == "vat_sex_judge":
        if (
            not value.answer_event
            or value.dislike_event
            or answer.options not in (("accept",), ("dislike",), ("punish",))
            or answer.fields
            or answer.flag is not None
        ):
            raise WorkflowError(
                "Judge your actual answer; only dislike may lead to your real Punishment"
            )
        discipline = (
            _discipline(
                game,
                c,
                state,
                actor=value.actor,
                chooser=value.target,
                source=value.id,
                event=event,
                action=action["id"],
            )
            if answer.options == ("punish",)
            else None
        )
        rules.put(
            state,
            value.model_copy(
                update=dict(
                    liked=answer.options == ("accept",),
                    dislike_event=event,
                    discipline=discipline,
                    phase="departure",
                )
            ),
        )
        game.request(c, action, value.counterpart, "vat_sex_depart")
    elif kind == "vat_sex_depart":
        raise WorkflowError(
            "REQUIRED_ACTUAL_DEPARTURE: use the actual counterpart departure controls"
        )
    else:
        raise WorkflowError("Recover the actual Vatgrown source choice")
    _finish(game, c, state, action, event)


apply = apply_choice


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = prove(game, c, state, action["data"]["vatgrown_sex"]["session"])
    sheet = state.sheets[value.actor.entity]
    teacher = state.sheets.get(value.target.entity) if value.target.kind == "pilot" else None
    from girlframe.engine.m3_leviathan_obsession import require_unlocked
    from girlframe.services.m3_learned_plays import SUPPORTED

    replacements = []
    for identity in sheet.identities:
        if identity.protected:
            continue
        try:
            require_unlocked(sheet.identities, (identity.id,))
        except ValueError:
            continue
        replacements.append(dict(id=identity.id, name=identity.name))
    return dict(
        session=value.id,
        kind=row["kind"],
        tier=value.tier,
        effects=rules.EFFECTS,
        identities=[dict(id=x.id, name=x.name) for x in teacher.identities] if teacher else [],
        replacements=replacements,
        required=2 if value.tier in ("mid", "high") else 1,
        plays=[
            dict(id=rule, label=play.replace("_", " ").title())
            for rule, (play, book) in SUPPORTED.items()
            if teacher and teacher.girl == book and has_rule(teacher, rule, book)
        ],
        question=json.loads(row["body_json"]).get("question"),
        discipline=value.discipline,
        departed=bool(value.departed_event),
    )


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    if action["data"].get("vatgrown_sex"):
        from girlframe.services.m3_role_punishments import synchronize as sync_punishment

        sync_punishment(game, c, action, event)
        state = load_state(c, game.store.campaign_id)
        value = prove(game, c, state, action["data"]["vatgrown_sex"]["session"])
        if value.changeling_source is not None:
            from girlframe.services.m3_changeling_sex import synchronize_session

            synchronize_session(game, c, state, value.id, event)


def prove_learned_play(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.LearnedPlay:
    from girlframe.services.m3_learned_plays import SUPPORTED

    value = _get(state, rules.LearnedPlay, identity)
    born = _history(c, game, value.event)
    source = prove(game, c, state, value.session)
    selection = next(
        (
            x
            for x in rules.records(born, rules.Selection)
            if x.session == source.id and x.event == value.event and "play" in x.options
        ),
        None,
    )
    if (
        value not in rules.records(born, rules.LearnedPlay)
        or value.actor != source.actor
        or value.teacher != source.target
        or selection is None
        or selection.fields.get("play") != value.rule_id
        or value.rule_id not in SUPPORTED
        or value.teacher.kind != "pilot"
    ):
        raise WorkflowError("Recover the actual source-owned immutable learned Play")
    teacher = born.sheets.get(value.teacher.entity)
    owner = source.counterpart if source.tier == "high" else source.caster
    answer = _response(
        game, c, selection.action, selection.choice, selection.event, owner, "vat_sex_learn"
    )
    if (
        answer.options != selection.options
        or answer.fields != selection.fields
        or teacher is None
        or teacher.character_id != value.teacher.incarnation
        or teacher.girl != SUPPORTED[value.rule_id][1]
        or not has_rule(teacher, value.rule_id, SUPPORTED[value.rule_id][1])
    ):
        raise WorkflowError(
            "The actual original teacher and printed author must supply this one-use Play"
        )
    return value


def side_condition(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> rules.SideCondition | None:
    for saved in rules.records(state, rules.SideCondition):
        if saved.actor != actor:
            continue
        if saved.released_event:
            released = _get(_history(c, game, saved.released_event), rules.SideCondition, saved.id)
            session = prove(game, c, state, saved.session)
            _event(game, c, saved.released_event, ("m3.vatgrown_sent_away",), session.counterpart)
            if released.released_event != saved.released_event:
                raise WorkflowError("Recover the original counterpart's actual source release")
        if saved.left_event:
            actual = game.action(c, saved.leaving_action or "")
            if (
                actual["state"] != "complete"
                or actual["data"]["play"] != "disobey_orders"
                or not actual["data"].get("result", {}).get("can_disobey")
                or actual["data"].get("vatgrown_leaving", {}).get("session") != saved.session
            ):
                raise WorkflowError("Recover the actual completed successful departure Play")
    active = [
        x
        for x in rules.records(state, rules.SideCondition)
        if x.actor == actor and not x.released_event and not x.left_event
    ]
    if len(active) > 1:
        raise WorkflowError("Resolve the original active side condition before another high source")
    if not active:
        return None
    value = active[0]
    source = prove(game, c, state, value.session)
    birth = _get(_history(c, game, value.event), rules.SideCondition, value.id)
    if (
        source.tier != "high"
        or source.actor != value.actor
        or source.target != value.counterpart
        or source.effect_event != value.event
        or any(
            getattr(value, key) != getattr(birth, key)
            for key in ("id", "session", "actor", "counterpart", "event")
        )
    ):
        raise WorkflowError("Preserve the actual high source's original staying-by-side condition")
    return value


def leaving_order(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    departure: str,
    channel: int,
) -> dict[str, Any] | None:
    value = side_condition(game, c, state, actor)
    if value is None:
        return None
    source = prove(game, c, state, value.session)
    if not departure.strip() or channel != source.cast.channel or value.leaving_action:
        raise WorkflowError("Bind the actual single departure from the original counterpart")
    return dict(
        session=source.id,
        issuer=value.counterpart.model_dump(mode="json"),
        target=value.actor.model_dump(mode="json"),
        source_event=value.event,
        departure=departure,
        context="Leave the actual original counterpart's side",
    )


def complete_departure(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("vatgrown_leaving")
    if meta is None:
        raise WorkflowError("Recover the actual source-bound departure order")
    source = prove(game, c, state, meta["session"])
    value = side_condition(game, c, state, source.actor)
    if (
        value is None
        or action["actor_id"] != source.actor.entity
        or action["data"]["play"] != "disobey_orders"
        or action["state"] != "complete"
        or not action["data"].get("result", {}).get("can_disobey")
        or not action["data"].get("receipt")
        or meta.get("issuer") != source.target.model_dump(mode="json")
        or meta.get("target") != source.actor.model_dump(mode="json")
        or meta.get("source_event") != value.event
        or not meta.get("departure")
    ):
        raise WorkflowError(
            "Only the actual successful source-bound Disobey permits this departure"
        )
    _roll_source(game, c, action)
    rules.put(
        state,
        value.model_copy(
            update=dict(departure=meta["departure"], leaving_action=action["id"], left_event=event)
        ),
    )


def validate_counterpart_departure(
    game: GameService, c: Connection, state: GameState, session: str, event: str
) -> ActorRef:
    value = prove(game, c, state, session)
    if (
        value.tier != "low"
        or not value.dislike_event
        or value.departed_event
        or value.discipline
        and not _get(state, rules.Discipline, value.discipline).completed_event
    ):
        raise WorkflowError(
            "Complete the actual owned answer judgment and any chosen Punishment before departure"
        )
    if not any(
        x.id == value.cast.id
        and x.open
        and any(r.actor == value.target and r.controller == value.counterpart for r in x.roles)
        for x in state.scene_casts
    ):
        raise WorkflowError("The original counterpart must actually leave their source role")
    return value.target


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    value = _get(state, rules.Discipline, case.source_work or "")
    born = _get(_history(c, game, value.event), rules.Discipline, value.id)
    if (
        value.model_dump(exclude={"completed_event"})
        != born.model_dump(exclude={"completed_event"})
        or case.source_kind != "vatgrown_plays"
        or case.id != value.case
        or case.source_event != value.event
        or case.subject != value.actor
        or case.executor != value.chooser
        or case.chooser != value.chooser
        or case.chooser_controller != value.controller
    ):
        raise WorkflowError("Recover this actual original Vatgrown discipline source and chooser")
    session = next((x for x in rules.records(state, rules.Session) if x.id == value.source), None)
    if session:
        prove(game, c, state, session.id)
        if (
            session.discipline != value.id
            or session.target != value.chooser
            or session.actor != value.actor
            or session.liked is not False
            or case.action != session.action
        ):
            raise WorkflowError(
                "Preserve the actual counterpart's disliked answer and optional Punishment"
            )
    else:
        violation = prove_violation(game, c, state, value.source)
        if (
            violation.discipline != value.id
            or violation.actor != value.actor
            or violation.disclosed_handler != value.chooser
            or violation.judgment_event != value.event
        ):
            raise WorkflowError(
                "Punishment requires actual disclosed/witnessed original rule evidence"
            )


def role_scope(c: Connection, game: GameService, case: Any) -> WorkScope:
    """Bind standalone discipline to real evidence, never a source string as a scene."""
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    discipline = _get(state, rules.Discipline, case.source_work)
    violation = prove_violation(game, c, state, discipline.source)
    if violation.kind == "unchaperoned_attempt":
        from girlframe.services.m3_vatgrown_travel import prove_violation_source

        source = prove_violation_source(game, c, state, violation)
        return WorkScope(scene_id=source.proposal.scene)
    return WorkScope(campaign_context=True)


def complete_role_case(c: Connection, game: GameService, case: Any, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    if not case.effect_event or case.completion_event != event:
        raise WorkflowError("Complete the actual chosen Punishment and its real effects/followups")
    value = _get(state, rules.Discipline, case.source_work)
    if value.completed_event:
        return
    source_event = str(uuid4())
    rules.put(state, value.model_copy(update=dict(completed_event=source_event)))
    game.event(
        c,
        case.executor_controller,
        "vatgrown-punished:" + case.id,
        "m3.vatgrown_punished",
        state,
        event_id=source_event,
        discipline=value.id,
        case=case.id,
    )


def rejection_allowed(
    state: GameState, actor: ActorRef, tag: Any = None, actual_resolution: Any = None
) -> bool:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    return not bool(
        sheet
        and sheet.character_id == actor.incarnation
        and has_rule(sheet, rules.EXPERIMENT, "VATGROWN")
    )


def prove_violation(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Violation:
    value = _get(state, rules.Violation, identity)
    born = _get(_history(c, game, value.event), rules.Violation, identity)
    if any(
        getattr(value, key) != getattr(born, key)
        for key in (
            "id",
            "actor",
            "counterpart",
            "kind",
            "source",
            "author",
            "event",
            "account",
            "witnesses",
        )
    ):
        raise WorkflowError(
            "Preserve the actual authored rule evidence, not an inferred private action"
        )
    if value.kind == "sex_attempt":
        source = prove(game, c, state, value.source)
        if (
            source.proposed_event != value.event
            or source.caster != value.author
            or source.actor != value.actor
            or source.target != value.counterpart
            or value.counterpart is None
            or value.counterpart.kind != "pilot"
        ):
            raise WorkflowError("Recover the actual voluntarily proposed forbidden Girl source")
        if value.performed_event:
            performed = _get(_history(c, game, value.performed_event), rules.Session, source.id)
            if (
                source.effect_event != value.performed_event
                or performed.effect_event != value.performed_event
            ):
                raise WorkflowError("Recover the actually accepted and rolled performed source")
    elif value.kind == "unchaperoned_attempt":
        from girlframe.services.m3_vatgrown_travel import prove_violation_source

        prove_violation_source(game, c, state, value)
    elif value.kind not in ("relationship_attempt", "relationship"):
        raise WorkflowError(
            "UNSUPPORTED_VATGROWN_VIOLATION: use an actual supported source producer"
        )
    if value.disclosed_event:
        disclosed = _get(_history(c, game, value.disclosed_event), rules.Violation, value.id)
        _event(game, c, value.disclosed_event, ("m3.vatgrown_violation_disclosed",), value.author)
        if disclosed.disclosed_handler != value.disclosed_handler:
            raise WorkflowError("Recover the real participant's explicit Handler disclosure")
    return value


def _activation(game: GameService, c: Connection, state: GameState, owner: ActorRef) -> str:
    events = c.execute(
        sa.select(t.events.c.id)
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m2.character_activated",
            t.events.c.actor_id == owner.entity,
        )
        .order_by(t.events.c.seq.desc())
    ).scalars()
    for event in events:
        born = _history(c, game, event)
        sheet = born.sheets.get(owner.entity)
        if sheet and sheet.character_id == owner.incarnation:
            return str(event)
    raise WorkflowError("Recover the genuine activated original Vatgrown rather than a draft")


def investors(
    game: GameService, c: Connection, state: GameState, owner: ActorRef
) -> tuple[rules.Investor, ...]:
    _vatgrown(game, c, state, owner, rules.INVESTMENT)
    sheet = state.sheets[owner.entity]
    setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
    initial = _activation(game, c, state, owner)
    created = _history(c, game, initial).sheets[owner.entity]
    if setup and setup.book == "VATGROWN":
        event, kind = setup.source_event, "transition"
        actual_sheet = _history(c, game, event).sheets[owner.entity]
        saved = actual_sheet.girl_runtime.setup if actual_sheet.girl_runtime else None
        if saved != setup or setup.handler is None or setup.handler_desires is None:
            raise WorkflowError("Recover the actual transition's original Investor authors")
        entries = [
            (ActorRef(kind="npc", entity=x.npc), tuple(DESIRES[i] for i in x.desires.slots))
            for x in setup.investors
        ]
        entries.append((setup.handler, tuple(DESIRES[i] for i in setup.handler_desires.slots)))
    else:
        event, kind = initial, "creation"
        details = created.review.creation.girl_details
        coordination = next(
            (
                x
                for x in created.review.coordination
                if x.role == "vatgrown_handler" and x.owner == int(owner.entity)
            ),
            None,
        )
        if (
            details is None
            or coordination is None
            or coordination.desires is None
            or state.world is None
        ):
            raise WorkflowError(
                "Recover actual initial NPC links and the Handler-authored Investor desires"
            )
        entries = []
        for selected in details.investors:
            link = next(
                (
                    x
                    for x in state.world.starting_npc_links
                    if x.owner == int(owner.entity)
                    and x.character_id == owner.incarnation
                    and x.slot == selected.npc_slot
                ),
                None,
            )
            if link is None:
                raise WorkflowError(
                    "Bind every actual starting NPC Investor before Prime Investment"
                )
            entries.append(
                (
                    ActorRef(kind="npc", entity=link.npc),
                    tuple(DESIRES[i] for i in selected.desires.slots),
                )
            )
        handler = active_handler(_history(c, game, initial))
        if handler is None or handler.entity != str(coordination.author):
            raise WorkflowError("Recover the original accepted Handler Investor persona")
        entries.append((handler, tuple(DESIRES[i] for i in coordination.desires.slots)))
    result = []
    for actor, desires in entries:
        identity = rules.identity("investor", owner.token, actor.token)
        stored = next((x for x in rules.records(state, rules.Investor) if x.id == identity), None)
        actual = resolve(
            state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if not actual.alive:
            continue
        if stored:
            if stored.owner != owner or stored.actor != actor or stored.event != event:
                raise WorkflowError("Preserve actual original Investor lineage")
            if stored.changes:
                latest = _get(_history(c, game, stored.changes[-1]), rules.Investor, stored.id)
                if latest.desires != stored.desires or latest.changes != stored.changes:
                    raise WorkflowError("Recover the actual authored current Investor desires")
            elif stored.desires != desires:
                raise WorkflowError("Initial Investor desires need their original actual authors")
            result.append(stored.model_copy(update=dict(controller=actual.controller)))
        else:
            result.append(
                rules.Investor(
                    id=identity,
                    owner=owner,
                    actor=actor,
                    controller=actual.controller,
                    event=event,
                    source=cast(Any, kind),
                    desires=desires,
                )
            )
    for item in rules.records(state, rules.Investor):
        if item.owner == owner and item.source == "added" and item.added_event:
            actual = resolve(
                state,
                item.actor,
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            )
            if actual.alive:
                result.append(item.model_copy(update=dict(controller=actual.controller)))
    return tuple(result)


def _period_source(
    game: GameService, c: Connection, state: GameState, period: Period, owner: int
) -> tuple[ActorRef, str, int, str]:
    progress = period.progress.get(str(owner))
    if (
        progress is None
        or progress.roll is None
        or progress.action_id is None
        or progress.roll.source != "status"
        or progress.roll.stage != "choices"
    ):
        raise WorkflowError("Use the actual original ordinary Go-OffDuty result")
    actor = current_ref(state, owner)
    if period.character_ids.get(str(owner)) != actor.incarnation:
        raise WorkflowError("The actual period belongs to the original Vatgrown")
    _vatgrown(game, c, state, actor, rules.INVESTMENT)
    action = game.action(c, progress.action_id)
    if action["actor_id"] != str(owner) or action["data"]["play"] != "go_off_duty":
        raise WorkflowError("Recover the actual original Go-OffDuty source action")
    roll_event, total = _roll_source(game, c, action)
    if total != progress.roll.total:
        raise WorkflowError("Recover the actual final source Tag-adjusted OffDuty total")
    return actor, progress.action_id, total, roll_event


def synchronize_off_duty(
    game: GameService, c: Connection, state: GameState, period: Period, event: str
) -> None:
    approval = game.store.policy.m3_approval
    if (
        approval is None
        or "plays" not in approval.subsystems
        or game.store.policy.owner_m3_rulings is None
    ):
        return
    try:
        registry = Access(game.store).registry
        if (
            registry is None
            or approval.registry_sha256 != digest(registry)
            or (approval.scope == "core_complete" and registry.coverage != "RULES_COMPLETE")
        ):
            return
        registry.require_available(rules.INVESTMENT)
    except (ValueError, WorkflowError):
        return
    for owner in period.pilots:
        sheet = state.sheets.get(str(owner))
        progress = period.progress.get(str(owner))
        if (
            sheet is None
            or not has_rule(sheet, rules.INVESTMENT, "VATGROWN")
            or progress is None
            or progress.roll is None
            or progress.action_id is None
            or progress.roll.source != "status"
            or progress.roll.stage != "choices"
        ):
            continue
        actor, action, total, rolled = _period_source(game, c, state, period, owner)
        identity = rules.identity("investment", period.id, actor.token)
        if total > 7 or any(x.id == identity for x in rules.records(state, rules.Investment)):
            continue
        rules.put(
            state,
            rules.Investment(
                id=identity,
                owner=actor,
                period=period.id,
                source_action=action,
                roll_event=rolled,
                total=total,
                event=event,
            ),
        )


def prime_scene(
    game: GameService,
    c: Connection,
    state: GameState,
    period: Period,
    owner: int,
    investor: ActorRef,
    kind: str,
    event: str,
) -> rules.Investment:
    actor, action, total, rolled = _period_source(game, c, state, period, owner)
    if kind != ("prime_high" if total >= 11 else "prime_mid") or total <= 7:
        raise WorkflowError("Choose the actual printed Investor scene for this real OffDuty tier")
    actual = next((x for x in investors(game, c, state, actor) if x.actor == investor), None)
    identity = rules.identity("investment", period.id, actor.token)
    if (
        actual is None
        or not actual.desires
        or any(x.id == identity for x in rules.records(state, rules.Investment))
    ):
        raise WorkflowError("Select one actual interested original Investor for this period")
    rules.put(state, actual)
    value = rules.Investment(
        id=identity,
        owner=actor,
        period=period.id,
        source_action=action,
        roll_event=rolled,
        total=total,
        event=event,
        investor=actual.id,
        actor=actual.actor,
        controller=actual.controller,
        kind=kind,
        phase="scene",
        scene_event=event,
        roles=(actor, investor),
    )
    rules.put(state, value)
    return value


def complete_prime_scene(
    game: GameService, c: Connection, state: GameState, period: Period, owner: int, event: str
) -> None:
    actor, _, _, _ = _period_source(game, c, state, period, owner)
    value = _get(state, rules.Investment, rules.identity("investment", period.id, actor.token))
    scene = period.progress[str(owner)].scene
    if (
        value.phase != "scene"
        or scene is None
        or scene.kind != value.kind
        or not set(scene.participants) <= set(scene.acknowledgements)
        or not {owner, value.controller} <= set(scene.participants)
    ):
        raise WorkflowError(
            "Complete the actual Investor scene and each original human's factual attendance"
        )
    for ref in value.roles:
        actual = resolve(
            state, ref, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        expected = owner if ref == value.owner else value.controller
        if actual.controller != expected or not actual.alive:
            raise WorkflowError(
                "Keep the original Investor scene role and controller through performance"
            )
    rules.put(
        state,
        value.model_copy(
            update=dict(
                scene_completed=event, phase="new_desire" if value.total >= 11 else "judgment"
            )
        ),
    )


def prove_investment(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Investment:
    value = _get(state, rules.Investment, identity)
    born = _get(_history(c, game, value.event), rules.Investment, identity)
    if any(
        getattr(value, key) != getattr(born, key)
        for key in (
            "id",
            "owner",
            "period",
            "source_action",
            "roll_event",
            "total",
            "event",
            "kind",
        )
    ):
        raise WorkflowError("Preserve actual period, original Girl and source roll")
    _, total = _roll_source(game, c, game.action(c, value.source_action))
    if total != value.total:
        raise WorkflowError("Preserve the actual original Go-OffDuty source result")
    if value.scene_completed:
        completed = _get(_history(c, game, value.scene_completed), rules.Investment, value.id)
        if completed.scene_completed != value.scene_completed or completed.actor != value.actor:
            raise WorkflowError("Recover the actual original Investor scene completion")
    if value.desire_event:
        changed = _get(_history(c, game, value.desire_event), rules.Investment, value.id)
        if (
            changed.desire != value.desire
            or changed.actor != value.actor
            or changed.investor != value.investor
            or changed.desire_event != value.desire_event
        ):
            raise WorkflowError("Recover the original actual desire removal or addition")
    if value.performance_action:
        if not value.performance_bound_event:
            raise WorkflowError("Bind the actual original performance before fulfilment")
        bound = _get(_history(c, game, value.performance_bound_event), rules.Investment, value.id)
        if bound.performance_action != value.performance_action:
            raise WorkflowError("Preserve the actual confirmed source performance")
        _event(
            game,
            c,
            value.performance_bound_event,
            ("m2.play_confirmed", "m3.play_confirmed"),
            int(value.owner.entity),
            value.performance_action,
        )
    if value.performance_event:
        completed = _get(
            _history(c, game, value.performance_record_event or value.performance_event),
            rules.Investment,
            value.id,
        )
        if completed.performance_event != value.performance_event:
            raise WorkflowError("Recover the actual source performance completion")
    if value.investor:
        actual = next(
            (x for x in investors(game, c, state, value.owner) if x.id == value.investor), None
        )
        if actual is None or actual.actor != value.actor or actual.controller != value.controller:
            raise WorkflowError("Recover the actual original Investor rather than an account alias")
    return value


def prove_offer(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.RequisitionOffer:
    """Immutable funding proof survives the real original recipient's later career ending."""
    value = _get(state, rules.RequisitionOffer, identity)
    original = _history(c, game, value.event)
    source = _get(original, rules.Investment, value.investment)
    birth = _get(_history(c, game, source.event), rules.Investment, source.id)
    stable = ("id", "owner", "period", "source_action", "roll_event", "total", "event", "kind")
    if value not in rules.records(original, rules.RequisitionOffer) or any(
        getattr(source, key) != getattr(birth, key) for key in stable
    ):
        raise WorkflowError("Preserve the immutable original Investor's actual funding source")
    _event(game, c, value.event, ("m3.vatgrown_investment_fulfilled",), source.controller)
    rolled, total = _roll_source(game, c, game.action(c, source.source_action))
    if (
        rolled != source.roll_event
        or total != source.total
        or total < 11
        or source.kind != "prime_high"
        or source.owner != value.actor
        or source.actor != value.investor
        or source.good is not True
        or source.judgment_event != value.event
        or not source.scene_completed
        or not source.performance_action
        or not source.performance_event
        or not source.performance_bound_event
        or value.kind not in ("creature_comforts", "privacy", "visiting_home", "retirement")
    ):
        raise WorkflowError(
            "Recover the actual fulfilled high Investor outcome and chosen Girl gift"
        )
    owner = original.sheets.get(value.actor.entity)
    if (
        owner is None
        or owner.character_id != value.actor.incarnation
        or not has_rule(owner, rules.INVESTMENT, "VATGROWN")
    ):
        raise WorkflowError("Fund only the actual original source-owned Vatgrown")
    investor = resolve(
        original, value.investor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if not investor.alive or investor.controller != source.controller:
        raise WorkflowError("The actual original Investor owns this funding choice")
    completed_scene = _get(_history(c, game, source.scene_completed), rules.Investment, source.id)
    if (
        completed_scene.scene_completed != source.scene_completed
        or completed_scene.actor != source.actor
    ):
        raise WorkflowError("Complete the actual original Investor scene first")
    child = game.action(c, source.performance_action)
    _roll_source(game, c, child)
    _event(
        game,
        c,
        source.performance_bound_event,
        ("m2.play_confirmed", "m3.play_confirmed"),
        int(value.actor.entity),
        child["id"],
    )
    performed = _get(
        _history(c, game, source.performance_record_event or source.performance_event),
        rules.Investment,
        source.id,
    )
    if (
        child["state"] != "complete"
        or child["actor_id"] != value.actor.entity
        or child["data"].get("prepared", {}).get("source_work") != source.id
        or performed.performance_event != source.performance_event
        or performed.performance_action != child["id"]
    ):
        raise WorkflowError("The new desire needs its genuine bound completed performance")
    return value


def prepare_investment_performance(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not prepared.source_work or not any(
        x.id == prepared.source_work for x in rules.records(state, rules.Investment)
    ):
        return None
    value = prove_investment(game, c, state, prepared.source_work)
    _access(game, c, viewer, rules.INVESTMENT)
    if (
        value.owner != current_ref(state, viewer.user_id)
        or value.phase != "fulfil"
        or not value.desire_event
        or value.performance_action
        or prepared.parent
        or prepared.off_duty_id
        or prepared.order_id
    ):
        raise WorkflowError("The original Vatgrown must actually perform the new Investor desire")
    scene = _cast(game, c, state, channel)
    if not any(r.actor == value.owner and r.controller == viewer.user_id for r in scene.roles):
        raise WorkflowError("Use the actual performer's real source scene")
    return dict(
        investment=value.id,
        actor=value.owner.model_dump(mode="json"),
        controller=viewer.user_id,
        cast=scene.model_dump(mode="json"),
        table=sorted(
            {x.controller for x in scene.roles}
            | ({scene.facilitator} if scene.facilitator else set())
        ),
    )


def bind_investment_performance(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    scope = action["data"]["investment_performance"]
    value = prove_investment(game, c, state, scope["investment"])
    if (
        value.performance_action
        or action["actor_id"] != value.owner.entity
        or action.get("parent_id")
    ):
        raise WorkflowError("Bind the original Vatgrown's actual single performance")
    rules.put(
        state,
        value.model_copy(
            update=dict(performance_action=action["id"], performance_bound_event=event)
        ),
    )


def complete_investment_performance(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    scope = action["data"].get("investment_performance")
    if scope is None:
        return False
    value = prove_investment(game, c, state, scope["investment"])
    if (
        value.performance_action != action["id"]
        or action["actor_id"] != value.owner.entity
        or action["state"] != "complete"
        or not action["data"].get("receipt")
        or not action["data"].get("result")
        or game.pending(c, action["id"])
    ):
        raise WorkflowError("Complete the genuine performance and every real ordinary consequence")
    _roll_source(game, c, action)
    if value.performance_event:
        if value.performance_event != event:
            raise WorkflowError("This source already has its actual completed performance")
        return True
    post = (
        c.scalar(
            sa.select(t.events.c.id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        is not None
    )
    record_event = str(uuid4()) if post else event
    rules.put(
        state,
        value.model_copy(
            update=dict(
                performance_event=event,
                performance_record_event=record_event,
                phase="fulfilment_judgment",
            )
        ),
    )
    if post:
        game.event(
            c,
            int(action["actor_id"]),
            "vatgrown-performance:" + action["id"],
            "m3.vatgrown_performance_completed",
            state,
            event_id=record_event,
            investment=value.id,
            action_id=action["id"],
        )
    return True


def require_period_complete(
    game: GameService, c: Connection, state: GameState, period: Period
) -> None:
    for value in rules.records(state, rules.Investment):
        if value.period == period.id and not value.completed_event:
            prove_investment(game, c, state, value.id)
            raise WorkflowError(
                "REQUIRED_PRIME_INVESTMENT: finish the actual Investor outcome "
                "before ending this period"
            )


class VatgrownPlaysService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _mutate(
        self,
        viewer: GuildViewer,
        key: str,
        name: str,
        expected: int,
        payload: dict[str, Any],
        change_state: Callable[[Connection, GameState, str], dict[str, Any]],
        rule: str = rules.SEX,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected:
                raise WorkflowError("STALE_VATGROWN: reopen the actual current source")
            event = str(uuid4())
            result = change_state(c, state, event)
            self.game.event(
                c, viewer.user_id, key, name, state, event_id=event, source=result.get("id")
            )
            if name == "m3.vatgrown_violation_judged" and result.get("punishment"):
                from girlframe.services.m3_role_punishments import synchronize as sync_punishment

                sync_punishment(self.game, c, None, event)
            if result.get("id"):
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(self.game, c, state, result["id"], event)
            return result

        try:
            return self.store._write(
                viewer,
                key,
                name,
                dict(expected=expected, **payload),
                operation,
                auto_audit=False,
                authorize=lambda c: _access(self.game, c, viewer, rule),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

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
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe only the actual voluntary source proposal")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            if self.game.pending_actions(c):
                raise WorkflowError("Finish pending Plays before proposing the actual source")
            actor = current_ref(state, viewer.user_id)
            own = (
                _vatgrown(self.game, c, state, actor, rules.SEX)
                if bonded_source is None
                else _native(self.game, c, state, actor)
            )
            if bonded_source is not None:
                from girlframe.services.m3_bonded import admit_delegation

                admit_delegation(self.game, c, state, actor, target, rules.SEX, bonded_source)
            other = resolve(
                state, target, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if own.vessel_id is None or other.vessel_id is None:
                raise WorkflowError(
                    "UNSUPPORTED_VATGROWN_BODY: establish the actual original counterpart body"
                )
            if side_condition(self.game, c, state, actor):
                raise WorkflowError("Resolve the actual original staying-by-side condition first")
            scene = _cast(self.game, c, state, channel)
            assert self.store.policy.m3_approval is not None
            value = rules.Session(
                id=str(uuid4()),
                actor=actor,
                bonded_source=bonded_source,
                changeling_source=changeling_source,
                target=target,
                caster=viewer.user_id,
                counterpart=other.controller,
                cast=scene,
                registry=self.store.policy.m3_approval.registry_sha256,
                actor_vessel=own.vessel_id,
                target_vessel=other.vessel_id,
                proposed_event=event,
                proposal=account.strip(),
            )
            _contact(self.game, c, state, value)
            if scene not in state.scene_casts:
                state.scene_casts.append(scene)
            rules.put(state, value)
            if changeling_source is not None:
                from girlframe.services.m3_changeling_sex import bind_source

                bind_source(
                    self.game,
                    c,
                    state,
                    changeling_source,
                    value.id,
                    rules.SEX,
                    value.proposed_event,
                )
            if bonded_source is not None:
                from girlframe.services.m3_bonded import bind_delegation

                bind_delegation(self.game, c, state, bonded_source, value.id, rules.SEX, event)
            if target.kind == "pilot" and has_rule(
                state.sheets[actor.entity], rules.EXPERIMENT, "VATGROWN"
            ):
                rules.put(
                    state,
                    rules.Violation(
                        id=rules.identity("sex-attempt", value.id),
                        actor=actor,
                        counterpart=target,
                        kind="sex_attempt",
                        source=value.id,
                        author=viewer.user_id,
                        event=event,
                        account=account.strip(),
                    ),
                )
            return dict(id=value.id)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_sex_invited",
            expected,
            dict(channel=channel, target=target.model_dump(mode="json"), account=account)
            | ({"bonded_source": bonded_source} if bonded_source is not None else {})
            | ({"changeling_source": changeling_source} if changeling_source is not None else {}),
            operation,
        )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        if type(accept) is not bool or not account.strip() or len(account) > 1200:
            raise WorkflowError("Give only your actual voluntary source response")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove(self.game, c, state, identity)
            if (
                viewer.user_id != value.counterpart
                or value.phase != "invited"
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Answer your own actual original invitation")
            _contact(self.game, c, state, value)
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
            return dict(id=identity, phase="accepted" if accept else "declined")

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_sex_consent",
            expected,
            dict(id=identity, accept=accept, account=account),
            operation,
        )

    def depart(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Record only the actual original counterpart's departure")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove(self.game, c, state, identity)
            if viewer.user_id != value.counterpart:
                raise WorkflowError("The actual counterpart owns their own source departure")
            from girlframe.services.m3_vatgrown_support import depart_counterpart

            depart_counterpart(self.game, c, state, identity, event)
            rules.put(state, value.model_copy(update=dict(departed_event=event, phase="learning")))
            action = self.game.action(c, value.action or "")
            rows = [
                x
                for x in self.game.pending(c, action["id"])
                if x["kind"] == "vat_sex_depart" and x["actor_id"] == str(value.counterpart)
            ]
            if len(rows) != 1:
                raise WorkflowError("Recover the actual original required departure row")
            row = rows[0]
            c.execute(
                t.m2["m2_choices"]
                .update()
                .where(
                    t.m2["m2_choices"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_choices"].c.id == row["id"],
                )
                .values(
                    state="answered",
                    revision=row["revision"] + 1,
                    body_json=json.dumps(
                        dict(
                            completion_event=event,
                            departed_actor=value.target.model_dump(mode="json"),
                        )
                    ),
                )
            )
            self.game.request(c, action, value.caster, "vat_sex_learn")
            self.game.save_action(c, action, state="awaiting_choices")
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_counterpart_departed",
            expected,
            dict(id=identity, account=account),
            operation,
        )

    def send_away(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Record the actual original counterpart sending the Vatgrown away")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            source = prove(self.game, c, state, identity)
            value = side_condition(self.game, c, state, source.actor)
            if source.counterpart != viewer.user_id or value is None or value.session != source.id:
                raise WorkflowError(
                    "Only the actual original counterpart releases this staying condition"
                )
            rules.put(state, value.model_copy(update=dict(released_event=event)))
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_sent_away",
            expected,
            dict(id=identity, account=account),
            operation,
        )

    def disclose(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe your actual explicit disclosure")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_violation(self.game, c, state, identity)
            handler = active_handler(state)
            if viewer.user_id != value.author or handler is None or value.disclosed_event:
                raise WorkflowError(
                    "Only the original participant may disclose this private source once"
                )
            rules.put(
                state,
                value.model_copy(update=dict(disclosed_event=event, disclosed_handler=handler)),
            )
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_violation_disclosed",
            expected,
            dict(id=identity, account=account),
            operation,
            rules.EXPERIMENT,
        )

    def judge_violation(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        punish: bool,
        account: str,
    ) -> dict[str, Any]:
        if type(punish) is not bool or not account.strip() or len(account) > 1200:
            raise WorkflowError("Judge the actual known evidence and optional real Punishment")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_violation(self.game, c, state, identity)
            handler = active_handler(state)
            if (
                handler is None
                or handler.entity != str(viewer.user_id)
                or value.disclosed_handler != handler
                or not value.disclosed_event
                or value.judgment_event
            ):
                raise WorkflowError(
                    "Only the actual disclosed Handler may adjudicate this evidence"
                )
            discipline = (
                _discipline(
                    self.game,
                    c,
                    state,
                    actor=value.actor,
                    chooser=handler,
                    source=value.id,
                    event=event,
                    action=None,
                )
                if punish
                else None
            )
            rules.put(
                state, value.model_copy(update=dict(judgment_event=event, discipline=discipline))
            )
            return dict(id=identity, punishment=discipline)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_violation_judged",
            expected,
            dict(id=identity, punish=punish, account=account),
            operation,
            rules.EXPERIMENT,
        )

    def record_attempt(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        kind: str,
        counterpart: ActorRef | None,
        source: str,
        account: str,
    ) -> dict[str, Any]:
        if (
            kind not in ("relationship_attempt", "unchaperoned_attempt")
            or not account.strip()
            or len(account) > 1200
        ):
            raise WorkflowError(
                "Record an actual declared supported attempt, without arbitrary effects"
            )

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            _vatgrown(self.game, c, state, actor, rules.EXPERIMENT)
            if kind == "relationship_attempt":
                if counterpart is None or counterpart.kind != "pilot" or counterpart == actor:
                    raise WorkflowError(
                        "An actual forbidden relationship attempt addresses another real Girl"
                    )
                _native(self.game, c, state, counterpart)
            else:
                raise WorkflowError(
                    "UNSUPPORTED_UNCHAPERONED_ATTEMPT: use the actual travel proposal adapter"
                )
            identity = str(uuid4())
            rules.put(
                state,
                rules.Violation(
                    id=identity,
                    actor=actor,
                    counterpart=counterpart,
                    kind=kind,
                    source=source,
                    author=viewer.user_id,
                    event=event,
                    account=account.strip(),
                ),
            )
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_rule_attempted",
            expected,
            dict(
                kind=kind,
                counterpart=counterpart.model_dump(mode="json") if counterpart else None,
                source=source,
                account=account,
            ),
            operation,
            rules.EXPERIMENT,
        )

    def low_investor(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        investor: ActorRef,
        desire: str,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Choose the actual waning Investor and actual desire to remove")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_investment(self.game, c, state, identity)
            if (
                viewer.user_id != int(value.owner.entity)
                or value.total > 7
                or value.phase != "select"
            ):
                raise WorkflowError("Choose your own actual low Investor source")
            actual = next(
                (x for x in investors(self.game, c, state, value.owner) if x.actor == investor),
                None,
            )
            if actual is None or desire not in actual.desires:
                raise WorkflowError("Remove one actual current desire from the original Investor")
            rules.put(
                state,
                actual.model_copy(
                    update=dict(
                        desires=tuple(x for x in actual.desires if x != desire),
                        changes=actual.changes + (event,),
                    )
                ),
            )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        investor=actual.id,
                        actor=actual.actor,
                        controller=actual.controller,
                        desire=desire,
                        desire_event=event,
                        phase="low_tag",
                    )
                ),
            )
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_interest_waned",
            expected,
            dict(
                id=identity,
                investor=investor.model_dump(mode="json"),
                desire=desire,
                account=account,
            ),
            operation,
            rules.INVESTMENT,
        )

    def low_tag(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, label: str
    ) -> dict[str, Any]:
        if not label.strip() or len(label) > 120:
            raise WorkflowError("The actual waning Investor authors a real Tag")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_investment(self.game, c, state, identity)
            if (
                value.phase != "low_tag"
                or value.actor is None
                or viewer.user_id != value.controller
            ):
                raise WorkflowError("Only the actual selected original Investor gives this Tag")
            current = resolve(
                state,
                value.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if current.controller != viewer.user_id:
                raise WorkflowError("Recover the actual Investor controller")
            _copy(
                state,
                give_tag(
                    state,
                    profiles(c, self.store.campaign_id),
                    value.owner,
                    value.actor,
                    label.strip(),
                    "vatgrown-low-tag:" + value.id,
                    event,
                    (int(value.owner.entity), viewer.user_id),
                ),
            )
            rules.put(state, value.model_copy(update=dict(completed_event=event, phase="complete")))
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_low_tag",
            expected,
            dict(id=identity, label=label),
            operation,
            rules.INVESTMENT,
        )

    def judge_scene(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        good: bool,
        question: str,
        account: str,
    ) -> dict[str, Any]:
        if (
            type(good) is not bool
            or not account.strip()
            or len(account) > 1200
            or good
            and (not question.strip() or len(question) > 300)
        ):
            raise WorkflowError(
                "Judge actual performed work and offer a real addressed answer favour if good"
            )

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_investment(self.game, c, state, identity)
            if (
                value.phase != "judgment"
                or viewer.user_id != value.controller
                or value.actor is None
                or not value.scene_completed
            ):
                raise WorkflowError(
                    "Only the actual original Investor judges the completed mid scene"
                )
            if good:
                favour = rules.Favour(
                    id=rules.identity("favour", value.id),
                    investment=value.id,
                    actor=value.owner,
                    investor=value.actor,
                    controller=viewer.user_id,
                    question=question.strip(),
                    event=event,
                )
                rules.put(state, favour)
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        good=good, judgment_event=event, completed_event=event, phase="complete"
                    )
                ),
            )
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_scene_judged",
            expected,
            dict(id=identity, good=good, question=question, account=account),
            operation,
            rules.INVESTMENT,
        )

    def new_desire(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, desire: str, account: str
    ) -> dict[str, Any]:
        if not desire.strip() or len(desire) > 160 or not account.strip() or len(account) > 1200:
            raise WorkflowError("The original Investor authors their actual new desire")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_investment(self.game, c, state, identity)
            if (
                value.phase != "new_desire"
                or value.actor is None
                or viewer.user_id != value.controller
            ):
                raise WorkflowError("Only the actual original Investor adds this new desire")
            investor = next(
                x for x in investors(self.game, c, state, value.owner) if x.id == value.investor
            )
            if desire.casefold() in {x.casefold() for x in investor.desires}:
                raise WorkflowError("Add a genuinely new desire, preserving existing ones")
            rules.put(
                state,
                investor.model_copy(
                    update=dict(
                        desires=investor.desires + (desire.strip(),),
                        changes=investor.changes + (event,),
                    )
                ),
            )
            rules.put(
                state,
                value.model_copy(
                    update=dict(desire=desire.strip(), desire_event=event, phase="fulfil")
                ),
            )
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_new_desire",
            expected,
            dict(id=identity, desire=desire, account=account),
            operation,
            rules.INVESTMENT,
        )

    def fulfil(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        fulfilled: bool,
        account: str,
        *,
        kind: str = "creature_comforts",
    ) -> dict[str, Any]:
        if (
            type(fulfilled) is not bool
            or not account.strip()
            or len(account) > 1200
            or kind not in ("creature_comforts", "privacy", "visiting_home", "retirement")
        ):
            raise WorkflowError("Judge the actual completed performance against the new desire")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_investment(self.game, c, state, identity)
            if (
                value.phase != "fulfilment_judgment"
                or not value.performance_event
                or not value.performance_action
                or value.actor is None
                or viewer.user_id != value.controller
            ):
                raise WorkflowError(
                    "Only the actual Investor judges a genuinely completed performance"
                )
            actual = self.game.action(c, value.performance_action)
            if (
                actual["state"] != "complete"
                or not actual["data"].get("receipt")
                or not actual["data"].get("result")
            ):
                raise WorkflowError("Complete the actual performed Play and its real outcomes")
            if fulfilled:
                rules.put(
                    state,
                    rules.RequisitionOffer(
                        id=rules.identity("offer", value.id),
                        actor=value.owner,
                        investor=value.actor,
                        investment=value.id,
                        kind=kind,
                        event=event,
                    ),
                )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        good=fulfilled,
                        judgment_event=event,
                        completed_event=event,
                        phase="complete",
                    )
                ),
            )
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_investment_fulfilled",
            expected,
            dict(id=identity, fulfilled=fulfilled, account=account, kind=kind),
            operation,
            rules.INVESTMENT,
        )

    def favour_reply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        back_down: bool,
        answer: str,
    ) -> dict[str, Any]:
        if type(back_down) is not bool or not answer.strip() or len(answer) > 1200:
            raise WorkflowError("Actually answer the offered question, or explicitly back down")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = _get(state, rules.Favour, identity)
            source = prove_investment(self.game, c, state, value.investment)
            born = _get(_history(c, self.game, value.event), rules.Favour, value.id)
            if (
                viewer.user_id != value.controller
                or value.resolution_event
                or source.actor != value.investor
                or born.question != value.question
                or born.investor != value.investor
            ):
                raise WorkflowError(
                    "Only the actual original Investor performs or backs down from this offer"
                )
            actual = resolve(
                state,
                value.investor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if actual.controller != viewer.user_id:
                raise WorkflowError("Recover the changed original Investor controller first")
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        answer="" if back_down else answer.strip(),
                        answer_event=None if back_down else event,
                        backed_down=back_down,
                        resolution_event=event,
                    )
                ),
            )
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_favour_resolved",
            expected,
            dict(id=identity, back_down=back_down, answer=answer),
            operation,
            rules.INVESTMENT,
        )

    def favour_tag(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, give: bool, account: str
    ) -> dict[str, Any]:
        if type(give) is not bool or not account.strip() or len(account) > (120 if give else 1200):
            raise WorkflowError("Choose your actual optional Tag after the Investor backs down")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = _get(state, rules.Favour, identity)
            prove_investment(self.game, c, state, value.investment)
            if (
                viewer.user_id != int(value.actor.entity)
                or current_ref(state, viewer.user_id) != value.actor
                or value.backed_down is not True
                or not value.resolution_event
                or value.tag_event
            ):
                raise WorkflowError(
                    "The original Vatgrown owns this actual unspent favour-failure Tag"
                )
            born = _get(_history(c, self.game, value.resolution_event), rules.Favour, value.id)
            if born.backed_down is not True or born.resolution_event != value.resolution_event:
                raise WorkflowError("Recover the real original Investor's explicit back-down")
            if give:
                _copy(
                    state,
                    give_tag(
                        state,
                        profiles(c, self.store.campaign_id),
                        value.investor,
                        value.actor,
                        account.strip(),
                        "vatgrown-favour-tag:" + value.id,
                        event,
                        (viewer.user_id, value.controller),
                    ),
                )
            rules.put(state, value.model_copy(update=dict(tag_event=event)))
            return dict(id=identity, given=give)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_favour_tag",
            expected,
            dict(id=identity, give=give, account=account),
            operation,
            rules.INVESTMENT,
        )

    def propose_investor(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        investor: ActorRef,
        desires: tuple[str, ...],
        account: str,
    ) -> dict[str, Any]:
        if (
            not 1 <= len(desires) <= 2
            or len(set(desires)) != len(desires)
            or not set(desires) <= set(DESIRES)
            or not account.strip()
            or len(account) > 1200
        ):
            raise WorkflowError("Propose an actual new Investor and one or two printed desires")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            owner = current_ref(state, viewer.user_id)
            _vatgrown(self.game, c, state, owner, rules.INVESTMENT)
            if (
                investor == owner
                or investor.kind not in ("pilot", "npc")
                or any(x.actor == investor for x in investors(self.game, c, state, owner))
            ):
                raise WorkflowError(
                    "Choose a distinct real new Girl or actual existing NPC Investor"
                )
            actual = resolve(
                state, investor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if not actual.alive:
                raise WorkflowError("Use the actual living proposed Investor")
            if investor.kind == "pilot":
                _native(self.game, c, state, investor)
            else:
                introduced = c.scalar(
                    sa.select(t.events.c.id).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.kind == "m3.npc_introduced",
                        sa.func.json_extract(t.events.c.payload_json, "$.entity_id")
                        == investor.entity,
                    )
                )
                if introduced is None:
                    raise WorkflowError("Introduce the real new NPC through World controls first")
            identity = rules.identity("investor", owner.token, investor.token)
            if any(x.id == identity for x in rules.records(state, rules.Investor)):
                raise WorkflowError("This exact original Investor proposal already exists")
            rules.put(
                state,
                rules.Investor(
                    id=identity,
                    owner=owner,
                    actor=investor,
                    controller=actual.controller,
                    event=event,
                    source="added",
                    desires=desires,
                ),
            )
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_investor_proposed",
            expected,
            dict(investor=investor.model_dump(mode="json"), desires=desires, account=account),
            operation,
            rules.INVESTMENT,
        )

    def quote_investor(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        price: int | None,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Give the actual Handler consent and exact positive Girl price")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = _get(state, rules.Investor, identity)
            _vatgrown(self.game, c, state, value.owner, rules.INVESTMENT)
            handler = active_handler(state)
            if (
                handler is None
                or handler.entity != str(viewer.user_id)
                or value.source != "added"
                or value.quote_event
                or value.added_event
            ):
                raise WorkflowError(
                    "Only the current actual Handler may quote this exact Investor proposal"
                )
            born = _get(_history(c, self.game, value.event), rules.Investor, identity)
            if (
                born.owner != value.owner
                or born.actor != value.actor
                or born.desires != value.desires
            ):
                raise WorkflowError(
                    "Preserve the original actual proposed Investor and desire selection"
                )
            if (value.actor.kind == "pilot" and (type(price) is not int or price <= 0)) or (
                value.actor.kind == "npc" and price is not None
            ):
                raise WorkflowError(
                    "A Girl pays an exact positive Handler quote; "
                    "NPC introduction grants no fictitious spend"
                )
            rules.put(state, value.model_copy(update=dict(quote=price, quote_event=event)))
            return dict(id=identity, price=price)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_investor_quoted",
            expected,
            dict(id=identity, price=price, account=account),
            operation,
            rules.INVESTMENT,
        )

    def accept_investor(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Explicitly confirm the actual Investor and quoted voluntary spend")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = _get(state, rules.Investor, identity)
            _vatgrown(self.game, c, state, value.owner, rules.INVESTMENT)
            if value.source != "added" or not value.quote_event or value.added_event:
                raise WorkflowError("The actual Handler must consent and quote before acceptance")
            quoted = _history(c, self.game, value.quote_event)
            exact = _get(quoted, rules.Investor, identity)
            if (
                exact.quote != value.quote
                or exact.actor != value.actor
                or exact.owner != value.owner
                or active_handler(quoted) != active_handler(state)
            ):
                raise WorkflowError("Accept the actual original still-current Handler quote")
            if value.actor.kind == "pilot":
                if (
                    viewer.user_id != value.controller
                    or current_ref(state, viewer.user_id) != value.actor
                    or type(value.quote) is not int
                    or value.quote <= 0
                ):
                    raise WorkflowError(
                        "Only the actual paying Girl voluntarily accepts the exact positive quote"
                    )
                from girlframe.engine.m3_intracadre_marriage import debit, payment_for
                from girlframe.services.m3_intracadre_marriage import prepare_payment

                prepare_payment(
                    self.game,
                    c,
                    state,
                    viewer,
                    value.actor,
                    "vatgrown_investor",
                    value.quote,
                    detail=value.id,
                )
                debit(
                    state,
                    value.actor,
                    value.quote,
                    event=event,
                    source=value.id,
                    payment=payment_for(
                        state, value.actor, "vatgrown_investor", value.quote, detail=value.id
                    ),
                )
            elif (
                viewer.user_id != int(value.owner.entity)
                or current_ref(state, viewer.user_id) != value.owner
            ):
                raise WorkflowError(
                    "The original Vatgrown accepts the actually introduced NPC Investor"
                )
            rules.put(state, value.model_copy(update=dict(added_event=event)))
            return dict(id=identity)

        return self._mutate(
            viewer,
            key,
            "m3.vatgrown_investor_added",
            expected,
            dict(id=identity, account=account),
            operation,
            rules.INVESTMENT,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for session in rules.records(state, rules.Session):
            if viewer.user_id not in (session.caster, session.counterpart):
                continue
            side = next(
                (
                    x
                    for x in rules.records(state, rules.SideCondition)
                    if x.session == session.id and not x.released_event and not x.left_event
                ),
                None,
            )
            pending = (
                session.phase == "invited"
                and viewer.user_id == session.counterpart
                or session.phase == "accepted"
                and viewer.user_id == session.caster
                or session.phase == "departure"
                and viewer.user_id == session.counterpart
                or side is not None
            )
            result.append(
                dict(
                    id=session.id,
                    label="Actual Vatgrown staying-by-side source"
                    if side
                    else "Actual Vatgrown interaction",
                    revision=state.revision,
                    pending=pending,
                    phase="resolved"
                    if (session.completed_event and side is None) or session.phase == "declined"
                    else "pending",
                )
            )
        for investment in rules.records(state, rules.Investment):
            if viewer.user_id in (int(investment.owner.entity), investment.controller):
                owner = (
                    int(investment.owner.entity)
                    if investment.phase in ("select", "fulfil")
                    else investment.controller
                )
                result.append(
                    dict(
                        id=investment.id,
                        label="Actual Prime Investment: " + investment.phase,
                        revision=state.revision,
                        pending=not investment.completed_event and viewer.user_id == owner,
                        phase="resolved" if investment.completed_event else "pending",
                    )
                )
        for favour in rules.records(state, rules.Favour):
            if viewer.user_id in (int(favour.actor.entity), favour.controller):
                pending = (
                    not favour.resolution_event
                    and viewer.user_id == favour.controller
                    or favour.backed_down is True
                    and not favour.tag_event
                    and viewer.user_id == int(favour.actor.entity)
                )
                result.append(
                    dict(
                        id=favour.id,
                        label="Actual offered Investor favour",
                        revision=state.revision,
                        pending=pending,
                        phase="pending"
                        if not favour.resolution_event
                        or favour.backed_down
                        and not favour.tag_event
                        else "resolved",
                    )
                )
        for investor in rules.records(state, rules.Investor):
            if investor.source == "added" and viewer.user_id in (
                int(investor.owner.entity),
                investor.controller,
                state.handler,
            ):
                author = (
                    state.handler
                    if not investor.quote_event
                    else investor.controller
                    if investor.actor.kind == "pilot"
                    else int(investor.owner.entity)
                )
                result.append(
                    dict(
                        id=investor.id,
                        label="Actual Investor proposal",
                        revision=state.revision,
                        pending=not investor.added_event and viewer.user_id == author,
                        phase="resolved" if investor.added_event else "pending",
                    )
                )
        for violation in rules.records(state, rules.Violation):
            if (
                viewer.user_id == violation.author
                or violation.disclosed_handler
                and violation.disclosed_handler.entity == str(viewer.user_id)
            ):
                result.append(
                    dict(
                        id=violation.id,
                        label="Private actual rule evidence",
                        revision=state.revision,
                        pending=bool(
                            violation.disclosed_handler
                            and violation.disclosed_handler.entity == str(viewer.user_id)
                            and not violation.judgment_event
                        ),
                        phase="resolved" if violation.judgment_event else "pending",
                    )
                )
        for offer in rules.records(state, rules.RequisitionOffer):
            if offer.actor.entity == str(viewer.user_id):
                result.append(
                    dict(
                        id=offer.id,
                        label="Offered Creature Comforts",
                        revision=state.revision,
                        pending=True,
                        phase="pending",
                    )
                )
        return result

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return self._tasks(c, viewer)

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            session = next(
                (x for x in rules.records(state, rules.Session) if x.id == identity), None
            )
            if session:
                if viewer.user_id not in (session.caster, session.counterpart):
                    raise WorkflowError(
                        "Only original actual participants read this private source"
                    )
                value = prove(self.game, c, state, identity)
                side = next(
                    (x for x in rules.records(state, rules.SideCondition) if x.session == identity),
                    None,
                )
                runtime = state.sheets[value.actor.entity].girl_runtime
                return dict(
                    id=identity,
                    type="sex",
                    revision=state.revision,
                    session=value.model_dump(mode="json"),
                    side=side.model_dump(mode="json") if side else None,
                    copies=[
                        dict(text=x.text, id=x.id)
                        for x in rules.records(state, rules.IdentityCopy)
                        if x.session == identity
                    ],
                    learned=[
                        dict(
                            rule=x.rule_id,
                            id=x.id,
                            can_dose=(
                                x.rule_id == "girl.stim-blissed.dose-up"
                                and viewer.user_id == value.caster
                                and any(
                                    use.id == x.id
                                    and use.rolled_event is None
                                    and use.claimed_action is None
                                    for use in (runtime.learned_plays if runtime else ())
                                )
                            ),
                        )
                        for x in rules.records(state, rules.LearnedPlay)
                        if x.session == identity
                    ],
                    choices=[
                        dict(x)
                        for x in self.game.pending(c, value.action)
                        if x["actor_id"] == str(viewer.user_id)
                    ]
                    if value.action
                    else [],
                )
            investment = next(
                (x for x in rules.records(state, rules.Investment) if x.id == identity), None
            )
            if investment:
                if viewer.user_id not in (int(investment.owner.entity), investment.controller):
                    raise WorkflowError(
                        "This actual Investor outcome belongs only to its original parties"
                    )
                value2 = prove_investment(self.game, c, state, identity)
                return dict(
                    id=identity,
                    type="investment",
                    revision=state.revision,
                    investment=value2.model_dump(mode="json"),
                    investors=[
                        x.model_dump(mode="json")
                        for x in investors(self.game, c, state, investment.owner)
                    ],
                )
            favour = next((x for x in rules.records(state, rules.Favour) if x.id == identity), None)
            if favour:
                if viewer.user_id not in (int(favour.actor.entity), favour.controller):
                    raise WorkflowError(
                        "Only the actual addressed favour parties read this private offer"
                    )
                prove_investment(self.game, c, state, favour.investment)
                return dict(
                    id=identity,
                    type="favour",
                    revision=state.revision,
                    favour=favour.model_dump(mode="json"),
                )
            violation = next(
                (x for x in rules.records(state, rules.Violation) if x.id == identity), None
            )
            if violation:
                if viewer.user_id != violation.author and (
                    violation.disclosed_handler is None
                    or violation.disclosed_handler.entity != str(viewer.user_id)
                ):
                    raise WorkflowError("This actual rule evidence has not been disclosed to you")
                value3 = prove_violation(self.game, c, state, identity)
                return dict(
                    id=identity,
                    type="violation",
                    revision=state.revision,
                    violation=value3.model_dump(mode="json"),
                )
            investor = next(
                (x for x in rules.records(state, rules.Investor) if x.id == identity), None
            )
            if investor:
                if viewer.user_id not in (
                    int(investor.owner.entity),
                    investor.controller,
                    state.handler,
                ):
                    raise WorkflowError(
                        "This actual proposed investment belongs to its original parties"
                    )
                return dict(
                    id=identity,
                    type="investor",
                    revision=state.revision,
                    investor=investor.model_dump(mode="json"),
                )
            offer = _get(state, rules.RequisitionOffer, identity)
            if offer.actor.entity != str(viewer.user_id):
                raise WorkflowError("This offered Requisition belongs to its original recipient")
            prove_offer(self.game, c, state, identity)
            return dict(
                id=identity,
                type="offer",
                revision=state.revision,
                offer=offer.model_dump(mode="json"),
            )

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            targets, possible = [], []
            own_investors: list[dict[str, Any]] = []
            available = False
            try:
                actor = current_ref(state, viewer.user_id)
                _vatgrown(self.game, c, state, actor, rules.SEX)
                scene = _cast(self.game, c, state, channel)
                for role in scene.roles:
                    if role.actor == actor:
                        continue
                    actual = resolve(
                        state,
                        role.actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    if actual.alive:
                        possible.append(
                            dict(
                                ref=role.actor.model_dump(mode="json"),
                                id=role.actor.token,
                                label=actual.label,
                            )
                        )
                    if (
                        role.actor.kind == "pilot"
                        and actual.inside_frame is False
                        and actual.vessel_id
                    ):
                        targets.append(
                            dict(
                                ref=role.actor.model_dump(mode="json"),
                                id=role.actor.token,
                                label=actual.label,
                            )
                        )
                own_investors = [
                    x.model_dump(mode="json") for x in investors(self.game, c, state, actor)
                ]
                available = True
            except (ValueError, WorkflowError):
                pass
            return dict(
                channel=channel,
                revision=state.revision,
                can_invite=available and bool(targets),
                targets=targets,
                possible_investors=possible,
                investors=own_investors,
                tasks=self._tasks(c, viewer),
            )


def require_scene_allowed(
    game: GameService,
    c: Connection,
    state: GameState,
    period: Period,
    owner: int,
    actors: tuple[ActorRef, ...],
) -> None:
    for value in rules.records(state, rules.Investment):
        if (
            value.period == period.id
            and value.owner.entity == str(owner)
            and value.total <= 7
            and value.actor in actors
        ):
            prove_investment(game, c, state, value.id)
            raise WorkflowError(
                "This actual waning Investor cannot share your scene during this period"
            )


def synchronize_investment_performance(
    game: GameService, c: Connection, action: dict[str, Any], event: str
) -> None:
    if action["data"].get("investment_performance") and action["state"] == "complete":
        complete_investment_performance(
            game, c, load_state(c, game.store.campaign_id), action, event
        )
