"""Human-authored actual Stim intimacy, owned reciprocal drugs and real effects."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_stim_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import change, current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_dose_up import COMPONENTS, LABELS, SELF_RULE
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird import actor_tags, give_tag
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _audit, _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_oldgen_sex import _counterpart
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("stim_sex_drug", "stim_sex_effects", "stim_sex_optional")


def _copy(state: GameState, changed: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(changed, key))


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _physical_contact(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Session,
    *,
    pending_event: str | None = None,
) -> None:
    from girlframe.services.m3_bonded import admit_delegation
    from girlframe.services.m3_changeling_sex import admit_contact

    if (
        sum(
            x is not None
            for x in (value.changeling_source, value.bonded_source, value.learned_source)
        )
        > 1
    ):
        raise WorkflowError("Keep actual psychic contact separate from Bonded delegation")
    remote = admit_contact(
        game, c, state, value.actor, value.target, rules.RULE, value.changeling_source
    )
    from girlframe.services.m3_learned_sex import admit_source

    learned = admit_source(
        game,
        c,
        state,
        value.actor,
        value.target,
        rules.RULE,
        value.learned_source,
        pending_event=pending_event,
    )

    own, other = (
        resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)
        for ref in (value.actor, value.target)
    )
    cast = value.cast
    npc = value.target.kind == "npc"
    if npc:
        from girlframe.services.m3_stim_npc import contact

        contact(game, c, state, value, own, other, pending_event=pending_event)
    if (
        any(
            x.rules != "girl_frame" or x.offstage_source or x.custody not in (None, "free")
            for x in ((own,) if npc else (own, other))
        )
        or value.actor.kind != "pilot"
        or value.target.kind not in ("pilot", "npc")
        or value.actor == value.target
        or own.controller != value.caster
        or other.controller != value.counterpart
        or not (
            (has_rule(state.sheets[value.actor.entity], rules.RULE, "STIM-BLISSED") or learned)
            if value.bonded_source is None
            else admit_delegation(
                game, c, state, value.actor, value.target, rules.RULE, value.bonded_source
            )
        )
        or (
            not remote
            and not npc
            and any(x.inside_frame is not False or x.cell is None for x in (own, other))
        )
        or (not remote and own.cell != other.cell)
        or own.vessel_id != value.actor_vessel
        or other.vessel_id != value.target_vessel
        or not all(
            any(x.actor == ref and x.controller == human for x in cast.roles)
            for ref, human in ((value.actor, value.caster), (value.target, value.counterpart))
        )
    ):
        raise WorkflowError(
            "Use the actual original voluntary participants together in their current native bodies"
        )


def _contact(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Session,
    *,
    pending_event: str | None = None,
) -> None:
    _native(game, c, state, value.actor)
    _counterpart(game, c, state, value.target)
    if fingerprint(_cast(game, c, state, value.cast.channel)) != fingerprint(value.cast):
        raise WorkflowError("Recover the original actual voluntary source cast")
    _physical_contact(game, c, state, value, pending_event=pending_event)


def _selection(game: GameService, c: Connection, state: GameState, value: rules.Selection) -> None:
    born = _history(c, game, value.event)
    answer = _response(game, c, value.action, value.id, value.event, value.controller, value.kind)
    if (
        value not in rules.records(born, rules.Selection)
        or answer.options != value.options
        or answer.text != value.text
        or resolve(
            born, value.owner, profiles(c, game.store.campaign_id), require_current_profile=False
        ).controller
        != value.controller
    ):
        raise WorkflowError("Recover the actual original human's exact Stim choice")


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
            raise WorkflowError("Preserve this exact original learned Stim source")
    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import prove_source_link

        prove_source_link(
            game, c, state, value.changeling_source, value.id, value.actor, value.target, rules.RULE
        )

    proposed = _history(c, game, value.proposed_event)
    _audit(game, c, value.proposed_event, ("m3.stim_sex_invited",), value.caster)
    first = rules.get(proposed, identity)
    from girlframe.services.m3_bonded import prove_delegation
    from girlframe.services.m3_learned_bonded_stim import released_parent

    if not released_parent(game, c, state, value):
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
    if (
        any(getattr(first, key) != getattr(value, key) for key in stable)
        or value.cast not in proposed.scene_casts
    ):
        raise WorkflowError("Recover the original real Stim source and immutable cast")
    _physical_contact(game, c, proposed, first)
    if value.consent_event:
        accepted = _history(c, game, value.consent_event)
        _audit(game, c, value.consent_event, ("m3.stim_sex_consent",), value.counterpart)
        saved = rules.get(accepted, identity)
        if (
            saved.consent_account != value.consent_account
            or saved.consent_event != value.consent_event
            or saved.phase not in ("accepted", "declined")
            or saved.npc_contact != value.npc_contact
        ):
            raise WorkflowError("Recover the actual other human's original source confirmation")
    if value.npc_contact is not None:
        from girlframe.services.m3_stim_npc import _prove_npc_contact

        _prove_npc_contact(game, c, value)
    if value.action:
        if not value.bound_event or not value.consent_event:
            raise WorkflowError("Recover the accepted actual source before its genuine Play")
        bound = _history(c, game, value.bound_event)
        _audit(game, c, value.bound_event, ("m2.play_confirmed", "m3.play_confirmed"), value.caster)
        original = rules.get(bound, identity)
        action = game.action(c, value.action)
        frozen = action["data"].get("stim_sex", {})
        if (
            original.action != value.action
            or original.bound_event != value.bound_event
            or action["data"].get("play") != rules.PLAY
            or str(action["actor_id"]) != str(value.caster)
            or int(action["channel_id"]) != value.cast.channel
            or action["data"].get("prepared", {}).get("source_work") != value.id
            or action["data"].get("prepared", {}).get("target_actor")
            != value.target.model_dump(mode="json")
            or frozen.get("session") != value.id
            or frozen.get("actor") != value.actor.model_dump(mode="json")
            or frozen.get("target") != value.target.model_dump(mode="json")
            or frozen.get("caster") != value.caster
            or frozen.get("counterpart") != value.counterpart
            or frozen.get("cast") != value.cast.model_dump(mode="json")
            or frozen.get("cast_sha256") != fingerprint(value.cast)
            or frozen.get("table")
            != sorted(
                {x.controller for x in value.cast.roles}
                | ({value.cast.facilitator} if value.cast.facilitator is not None else set())
            )
        ):
            raise WorkflowError("Recover the original actual Sex Play binding")
        if value.effect_event:
            _, total = _roll_source(game, c, action)
            from girlframe.engine.m2 import tier

            if value.tier != tier(total):
                raise WorkflowError("Recover the genuine original Sex roll and result")
            ready = rules.get(_history(c, game, value.effect_event), identity)
            audit = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == game.store.campaign_id,
                        t.events.c.id == value.effect_event,
                    )
                )
                .mappings()
                .first()
            )
            if (
                ready.effect_event != value.effect_event
                or ready.tier != value.tier
                or ready.action != value.action
                or audit is None
                or audit["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
                or json.loads(audit["payload_json"]).get("action_id") != value.action
            ):
                raise WorkflowError("Recover the actual immutable Sex result source")
            selected_rows = [
                x for x in rules.records(state, rules.Selection) if x.action == value.action
            ]
            expected_phases = (
                ["low_drug", "low_effects", "low_optional"]
                if value.tier == "low"
                else ["target_drug", "actor_effects"]
                if value.tier == "mid"
                else ["target_drug", "self_drug", "actor_effects", "counter_effects"]
            )
            if (
                value.tier == "low"
                and len(selected_rows) >= 3
                and selected_rows[2].options == ("take",)
            ):
                expected_phases.append("low_self")
            if [x.phase for x in selected_rows] != expected_phases[: len(selected_rows)] or len(
                selected_rows
            ) > len(expected_phases):
                raise WorkflowError("Recover the exact printed sequence of owned Sex choices")
            for selected in selected_rows:
                _selection(game, c, state, selected)
                giver, target, owner = _roles(value.model_copy(update=dict(phase=selected.phase)))
                if (
                    selected.owner != giver
                    or selected.target != target
                    or selected.controller != owner
                ):
                    raise WorkflowError("Recover the actual original chooser and effect recipient")
                if selected.phase.endswith("effects"):
                    count = (
                        3
                        if selected.phase == "low_effects"
                        else 2
                        if selected.phase == "actor_effects" and value.tier == "high"
                        else 1
                    )
                    if (
                        selected.kind != "stim_sex_effects"
                        or len(selected.options) != count
                        or len(set(selected.options)) != count
                        or not set(selected.options) <= set(rules.EFFECTS)
                        or ("tag" in selected.options) != bool(selected.text.strip())
                    ):
                        raise WorkflowError("Recover every original printed actual effect choice")
                elif selected.phase == "low_optional":
                    if (
                        selected.kind != "stim_sex_optional"
                        or selected.options not in (("take",), ("decline",))
                        or selected.text
                    ):
                        raise WorkflowError("Recover the actual optional recipient drug choice")
                elif (
                    selected.kind != "stim_sex_drug"
                    or len(selected.options) != 1
                    or selected.options[0] not in COMPONENTS
                    or selected.text
                ):
                    raise WorkflowError("Recover the actual original single chosen drug")
            if value.completed_event:
                completed = rules.get(_history(c, game, value.completed_event), identity)
                if (
                    completed.completed_event != value.completed_event
                    or completed.phase != "complete"
                    or len(selected_rows) != len(expected_phases)
                ):
                    raise WorkflowError("Complete every genuine original Sex choice before closure")
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
        or channel != value.cast.channel
        or prepared.target is not None
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
    ):
        raise WorkflowError("Use this accepted actual voluntary Stim intimacy source")
    _contact(game, c, state, value)
    handler = active_handler(state)
    if handler is None or value.cast.facilitator is None:
        raise WorkflowError("Use the actual source Handler facilitator")
    from girlframe.services.m3_learned_bonded_stim import parent_lesson

    delegated_lesson = parent_lesson(state, value)
    return (
        dict(
            session=value.id,
            actor=value.actor.model_dump(mode="json"),
            target=value.target.model_dump(mode="json"),
            caster=value.caster,
            counterpart=value.counterpart,
            cast=value.cast.model_dump(mode="json"),
            cast_sha256=fingerprint(value.cast),
            table=sorted({x.controller for x in value.cast.roles} | {value.cast.facilitator}),
            handler=handler.model_dump(mode="json"),
            handler_controller=value.cast.facilitator,
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
    value = rules.get(state, action["data"]["stim_sex"]["session"])
    if value.phase != "accepted" or value.action or not event:
        raise WorkflowError("Bind the actual accepted Stim source once")
    rules.put(
        state, value.model_copy(update=dict(action=action["id"], bound_event=event, phase="active"))
    )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    value = prove(
        game, c, load_state(c, game.store.campaign_id), action["data"]["stim_sex"]["session"]
    )
    if value.action != action["id"] or viewer.user_id not in action["data"]["stim_sex"]["table"]:
        raise WorkflowError("Only the original table human owns this Stim response")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    value = rules.get(state, action["data"]["stim_sex"]["session"])
    if value.phase != "active" or value.caster != viewer.user_id or value.effect_event:
        raise WorkflowError("Roll the original accepted Stim source once")
    _contact(game, c, state, value)


def _request(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], phase: str
) -> None:
    value = rules.get(state, action["data"]["stim_sex"]["session"])
    rules.put(state, value.model_copy(update=dict(phase=phase)))
    owner = (
        value.counterpart
        if phase in ("low_drug", "low_effects", "low_optional", "low_self", "counter_effects")
        else value.caster
    )
    kind = (
        "stim_sex_effects"
        if phase.endswith("effects")
        else "stim_sex_optional"
        if phase == "low_optional"
        else "stim_sex_drug"
    )
    game.request(c, action, owner, kind)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.get(state, action["data"]["stim_sex"]["session"])
    if value.effect_event:
        raise WorkflowError("Resume saved Stim choices without rerolling")
    from girlframe.services.m3_gender_designation import offer_animal_tags

    if offer_animal_tags(game, c, state, action):
        action["data"]["gender_sex_deferred"] = True
        return
    level = action["data"]["result"]["tier"]
    rules.put(
        state,
        value.model_copy(update=dict(tier=level, effect_event=action["data"]["response_event"])),
    )
    _request(game, c, state, action, "low_drug" if level == "low" else "target_drug")


def _finish(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str | None = None,
) -> None:
    value = rules.get(state, action["data"]["stim_sex"]["session"])
    if game.pending(c, action["id"]) or action["state"] == "complete":
        return
    rules.put(
        state,
        value.model_copy(
            update=dict(phase="complete", completed_event=event or action["data"]["response_event"])
        ),
    )
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def _roles(value: rules.Session) -> tuple[ActorRef, ActorRef, int]:
    counter = value.phase in (
        "low_drug",
        "low_effects",
        "low_optional",
        "low_self",
        "counter_effects",
    )
    giver = value.target if counter else value.actor
    target = (
        value.target
        if value.phase in ("target_drug", "actor_effects", "low_self", "low_optional")
        else value.actor
    )
    return giver, target, value.counterpart if counter else value.caster


def _make_tag(
    game: GameService,
    c: Connection,
    state: GameState,
    target: ActorRef,
    giver: ActorRef,
    owner: int,
    identity: str,
    label: str,
    event: str,
    table: tuple[int, ...],
) -> TagState | WorldTag:
    if target.kind == "npc":
        _copy(
            state,
            give_tag(
                state,
                profiles(c, game.store.campaign_id),
                target,
                giver,
                label,
                identity,
                event,
                table,
            ),
        )
        value = next(x for x in actor_tags(state, target) if x.id == identity)
        assert isinstance(value, WorldTag)
        return value
    value = TagState(
        id=identity,
        label=label,
        giver=owner,
        giver_actor=giver,
        giver_character=giver.incarnation,
        observers=table,
    )
    state.sheets[target.entity].tags.append(value)
    state.sheets[target.entity].revision += 1
    return value


def _tag_provenance(
    tag: TagState | WorldTag,
    target: ActorRef,
    giver: ActorRef,
    owner: int,
    event: str,
    table: tuple[int, ...],
) -> bool:
    if target.kind == "npc":
        return isinstance(tag, WorldTag) and tag.giver_entity == giver.model_dump_json()
    return (
        isinstance(tag, TagState)
        and tag.giver == owner
        and tag.giver_actor == giver
        and tag.giver_character == giver.incarnation
        and tag.observers == table
    )


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    if row["kind"] not in KINDS:
        return False
    value = rules.get(state, action["data"]["stim_sex"]["session"])
    if value.target.kind == "npc":
        actual = _counterpart(game, c, state, value.target)
        if actual.controller != value.counterpart or actual.vessel_id != value.target_vessel:
            raise WorkflowError("Recover original NPC controller and body before source choices")
    giver, target, owner = _roles(value)
    if (
        int(row["actor_id"]) != owner
        or answer.denied
        or answer.fields
        or answer.number is not None
        or answer.flag is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use the actual original human's owned Stim choice")
    event = action["data"]["response_event"]
    if row["kind"] == "stim_sex_drug":
        if len(answer.options) != 1 or answer.options[0] not in COMPONENTS or answer.text:
            raise WorkflowError("Choose exactly one real Dose Up component")
    elif row["kind"] == "stim_sex_optional":
        if answer.options not in (("take",), ("decline",)) or answer.text:
            raise WorkflowError("Choose your actual optional self-drug or decline")
    else:
        count = (
            3
            if value.phase == "low_effects"
            else 2
            if value.phase == "actor_effects" and value.tier == "high"
            else 1
        )
        if (
            len(answer.options) != count
            or not set(answer.options) <= set(rules.EFFECTS)
            or ("tag" in answer.options) != bool(answer.text.strip())
        ):
            raise WorkflowError(
                "Choose the exact printed distinct effects and author any actual Tag"
            )
        if len(answer.text) > 120:
            raise WorkflowError("A Tag label has at most120 characters")
    if row["kind"] == "stim_sex_effects" and "orders" in answer.options and target.kind == "npc":
        raise WorkflowError(
            "NPC Orders need human adjudication; this source remains pending, "
            "with no effect applied"
        )
    selected = rules.Selection(
        id=row["id"],
        action=action["id"],
        owner=giver,
        target=target,
        phase=value.phase,
        controller=owner,
        kind=row["kind"],
        options=answer.options,
        text=answer.text,
        event=event,
    )
    rules.put(state, selected)
    if row["kind"] == "stim_sex_drug":
        component = answer.options[0]
        identity = "stim-sex-drug:" + action["id"] + ":" + target.token
        tag = _make_tag(
            game,
            c,
            state,
            target,
            giver,
            owner,
            identity,
            LABELS[component],
            event,
            tuple(action["data"]["stim_sex"]["table"]),
        )
        drug = rules.Drug.model_validate(
            dict(
                id=identity,
                session=value.id,
                action=action["id"],
                target=target,
                vessel=value.actor_vessel if target == value.actor else value.target_vessel,
                giver=giver,
                component=component,
                tag=tag,
                choice=row["id"],
                event=event,
            )
        )
        rules.put(state, drug)
        next_phase = (
            "low_effects"
            if value.phase == "low_drug"
            else "actor_effects"
            if value.phase == "self_drug" or value.tier == "mid"
            else "self_drug"
        )
        if value.phase == "low_self":
            _finish(game, c, state, action)
        else:
            _request(game, c, state, action, next_phase)
    elif row["kind"] == "stim_sex_optional":
        if answer.options == ("take",):
            _request(game, c, state, action, "low_self")
        else:
            _finish(game, c, state, action)
    else:
        drug = next(
            x
            for x in rules.records(state, rules.Drug)
            if x.action == action["id"] and x.target == target
        )
        for kind in answer.options:
            tag = None
            old = new = None
            identity = "stim-sex-effect:" + row["id"] + ":" + kind
            if kind == "bond":
                old = depth(state, giver, target)
                _copy(state, change(state, giver, target, 1, event))
                new = depth(state, giver, target)
            elif kind == "tag":
                tag = _make_tag(
                    game,
                    c,
                    state,
                    target,
                    giver,
                    owner,
                    identity,
                    answer.text.strip(),
                    event,
                    tuple(action["data"]["stim_sex"]["table"]),
                )
            rules.put(
                state,
                rules.Effect.model_validate(
                    dict(
                        id=identity,
                        action=action["id"],
                        kind=kind,
                        target=target,
                        giver=giver,
                        drug=drug.id,
                        choice=row["id"],
                        event=event,
                        tag=tag,
                        bond_before=old,
                        bond_after=new,
                    )
                ),
            )
        if value.phase == "low_effects":
            _request(game, c, state, action, "low_optional")
        elif value.phase == "actor_effects" and value.tier == "high":
            _request(game, c, state, action, "counter_effects")
        else:
            _finish(game, c, state, action)
    return True


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = rules.get(state, action["data"]["stim_sex"]["session"])
    if row["kind"] == "stim_sex_drug":
        return dict(
            options=tuple((x, LABELS[x]) for x in COMPONENTS), minimum=1, maximum=1, tag=False
        )
    if row["kind"] == "stim_sex_optional":
        return dict(
            options=(("take", "Take a drug yourself"), ("decline", "Do not take a drug")),
            minimum=1,
            maximum=1,
            tag=False,
        )
    count = (
        3
        if value.phase == "low_effects"
        else 2
        if value.phase == "actor_effects" and value.tier == "high"
        else 1
    )
    _, target, _ = _roles(value)
    return dict(
        options=(
            ("helpless", "Helpless while drugged"),
            (
                "orders",
                "NPC Orders: unsupported; pause for human adjudication"
                if target.kind == "npc"
                else "Give higher-Status Orders until drugs wear off",
            ),
            ("bond", "Deepen your actual Bond"),
            ("tag", "Give an authored Tag"),
        ),
        minimum=count,
        maximum=count,
        tag=True,
    )


def _drug(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Drug:
    drug = next((x for x in rules.records(state, rules.Drug) if x.id == identity), None)
    if drug is None:
        raise WorkflowError("Recover the genuine original Sex drug")
    session = prove(game, c, state, drug.session)
    born = _history(c, game, drug.event)
    selection = next(
        (x for x in rules.records(state, rules.Selection) if x.id == drug.choice), None
    )
    if selection is None:
        raise WorkflowError("Recover the actual original drug chooser")
    _selection(game, c, state, selection)
    giver, target, owner = _roles(session.model_copy(update=dict(phase=selection.phase)))
    if (
        drug not in rules.records(born, rules.Drug)
        or selection.kind != "stim_sex_drug"
        or selection.action != drug.action
        or selection.options != (drug.component,)
        or selection.target != drug.target
        or selection.event != drug.event
        or drug.action != session.action
        or drug.target != target
        or drug.giver != giver
        or selection.controller != owner
        or selection.owner != giver
        or drug.vessel
        != (session.actor_vessel if target == session.actor else session.target_vessel)
        or drug.tag.id != drug.id
        or drug.id != "stim-sex-drug:" + drug.action + ":" + target.token
        or drug.tag.label != LABELS[drug.component]
        or not _tag_provenance(
            drug.tag,
            target,
            giver,
            owner,
            drug.event,
            tuple(
                sorted(
                    {x.controller for x in session.cast.roles}
                    | (
                        {session.cast.facilitator}
                        if session.cast.facilitator is not None
                        else set()
                    )
                )
            ),
        )
        or drug.tag not in actor_tags(born, target)
    ):
        raise WorkflowError(
            "Recover the actual original chosen component, body, giver and drug Tag"
        )
    ends = [x for x in rules.records(state, rules.SceneEnd) if x.drug == drug.id]
    if len({x.scene for x in ends}) != len(ends) or len(ends) > drug.duration:
        raise WorkflowError("Count each real original drugged body's scene once")
    for index, end in enumerate(ends):
        ended = _history(c, game, end.event)
        source_event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == end.event
                )
            )
            .mappings()
            .first()
        )
        if (
            end not in rules.records(ended, rules.SceneEnd)
            or source_event is None
            or source_event["kind"] != "m2.scene_closed"
            or json.loads(source_event["payload_json"]).get("channel") != end.cast.channel
            or end.scene != end.cast.id
            or end.cast.open
            or end.cast not in ended.scene_casts
            or not any(x.actor == drug.target for x in end.cast.roles)
            or end.expired != (index + 1 >= drug.duration)
        ):
            raise WorkflowError(
                "Recover the actual source-owned drug expiry and closed recipient cast"
            )
    return drug


def prove_effect(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Effect:
    value = next((x for x in rules.records(state, rules.Effect) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the original source-owned Stim effect")
    born = _history(c, game, value.event)
    drug = _drug(game, c, state, value.drug)
    session = rules.get(state, drug.session)
    choice = next((x for x in rules.records(state, rules.Selection) if x.id == value.choice), None)
    if choice is None:
        raise WorkflowError("Recover the original actual effect chooser")
    _selection(game, c, state, choice)
    giver, target, owner = _roles(session.model_copy(update=dict(phase=choice.phase)))
    if (
        value not in rules.records(born, rules.Effect)
        or choice.kind != "stim_sex_effects"
        or value.kind not in choice.options
        or value.action != choice.action
        or value.event != choice.event
        or value.action != drug.action
        or value.target != drug.target
        or value.target != target
        or value.giver != giver
        or choice.owner != giver
        or choice.controller != owner
        or value.tag is not None
        and (
            value.kind != "tag"
            or value.tag.id != value.id
            or value.tag.label != choice.text.strip()
            or not _tag_provenance(
                value.tag,
                target,
                giver,
                owner,
                value.event,
                tuple(
                    sorted(
                        {x.controller for x in session.cast.roles}
                        | (
                            {session.cast.facilitator}
                            if session.cast.facilitator is not None
                            else set()
                        )
                    )
                ),
            )
            or value.tag not in actor_tags(born, target)
        )
    ):
        raise WorkflowError(
            "Recover the exact actual printed effect and its genuine owned response"
        )
    return value


def prove_drug_tag(
    game: GameService, c: Connection, state: GameState, owner: int, tag: TagState
) -> None:
    if tag.id.startswith("stim-sex-drug:"):
        drug = _drug(game, c, state, tag.id)
        if (
            drug.target != current_ref(state, owner)
            or not rules.active(state, drug)
            or tag.label != drug.tag.label
            or not isinstance(drug.tag, TagState)
            or tag.giver != drug.tag.giver
            or tag.giver_actor != drug.giver
            or tag.giver_character != drug.tag.giver_character
            or tag.observers != drug.tag.observers
        ):
            raise WorkflowError("Recover the actual active source-owned Sex drug Tag")
    elif tag.id.startswith("stim-sex-effect:"):
        value = prove_effect(game, c, state, tag.id)
        if (
            value.target != current_ref(state, owner)
            or value.tag is None
            or any(
                getattr(value.tag, key) != getattr(tag, key)
                for key in ("id", "label", "giver", "giver_actor", "giver_character", "observers")
            )
        ):
            raise WorkflowError("Recover the actual original authored Sex Tag")


def self_tag(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    person: int,
    tag: TagState,
) -> bool:
    if not tag.id.startswith("stim-sex-drug:") or person != int(action["actor_id"]):
        return False
    sheet = state.sheets.get(str(person))
    if sheet is None or not has_rule(sheet, SELF_RULE, "STIM-BLISSED"):
        return False
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(SELF_RULE)
    prove_drug_tag(game, c, state, person, tag)
    return True


def expire_scene(
    game: GameService, c: Connection, state: GameState, scene: dict[str, Any], event: str
) -> bool:
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    cast = next((x for x in state.scene_casts if x.id == scene["id"]), None)
    legacy = cast is None
    if cast is None:
        cast = CastService(ActorService(MissionService(game.store)))._legacy(c, scene)
        cast = cast.model_copy(update=dict(open=False, revision=cast.revision + 1))
    changed = False
    for drug in rules.records(state, rules.Drug):
        if rules.expired(state, drug.id) or not any(x.actor == drug.target for x in cast.roles):
            continue
        _drug(game, c, state, drug.id)
        before = [x for x in rules.records(state, rules.SceneEnd) if x.drug == drug.id]
        if any(x.scene == scene["id"] for x in before):
            continue
        npc = drug.target.kind == "npc"
        sheet = state.sheets.get(drug.target.entity) if not npc else None
        if npc:
            actual = _counterpart(game, c, state, drug.target)
            session = rules.get(state, drug.session)
            if actual.vessel_id != drug.vessel or actual.controller != session.counterpart:
                raise WorkflowError(
                    "Recover the actual original NPC body and controller before expiry"
                )
        if not npc and (
            sheet is None
            or sheet.character_id != drug.target.incarnation
            or resolve(
                state,
                drug.target,
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            ).vessel_id
            != drug.vessel
        ):
            raise WorkflowError("Recover the actual original drugged body before its scene closes")
        if any(x.id == drug.id and x.rejection_pending for x in actor_tags(state, drug.target)):
            raise WorkflowError("Finish the actual drug-Tag rejection before expiry")
        ends = len(before) + 1 >= drug.duration
        rules.put(
            state,
            rules.SceneEnd(
                id=str(uuid5(NAMESPACE_URL, drug.id + ":scene:" + scene["id"])),
                drug=drug.id,
                scene=scene["id"],
                cast=cast,
                event=event,
                expired=ends,
            ),
        )
        if ends:
            if npc:
                assert state.world is not None
                state.world = state.world.model_copy(
                    update={
                        "npcs": tuple(
                            x.model_copy(
                                update={"tags": tuple(t for t in x.tags if t.id != drug.id)}
                            )
                            if x.id == drug.target.entity
                            else x
                            for x in state.world.npcs
                        )
                    }
                )
            else:
                assert sheet is not None
                sheet.tags = [x for x in sheet.tags if x.id != drug.id]
                sheet.revision += 1
        changed = True
    if changed and legacy:
        state.scene_casts.append(cast)
    return changed


def order_authority(
    game: GameService, c: Connection, state: GameState, issuer: int, target: int
) -> dict[str, Any] | None:
    if str(issuer) not in state.sheets or str(target) not in state.sheets:
        return None
    first, second = current_ref(state, issuer), current_ref(state, target)
    for effect in reversed(rules.records(state, rules.Effect)):
        if effect.kind != "orders" or effect.giver != first or effect.target != second:
            continue
        proved = prove_effect(game, c, state, effect.id)
        drug = _drug(game, c, state, effect.drug)
        if rules.active(state, drug):
            return dict(
                effect=proved.id,
                issuer=first.model_dump(mode="json"),
                target=second.model_dump(mode="json"),
                drug=drug.id,
                event=proved.event,
            )
    return None


def valid_order(game: GameService, c: Connection, state: GameState, row: dict[str, Any]) -> bool:
    meta = json.loads(row["body_json"]).get("stim_sex")
    if meta is None:
        return False
    if (
        str(row["issuer_id"]) not in state.sheets
        or str(row["target_id"]) not in state.sheets
        or current_ref(state, int(row["issuer_id"])).model_dump(mode="json") != meta.get("issuer")
        or current_ref(state, int(row["target_id"])).model_dump(mode="json") != meta.get("target")
    ):
        raise WorkflowError(
            "Recover the original issued Order's actual people, not account aliases"
        )
    actions = t.m2["m2_actions"]
    action = (
        c.execute(
            sa.select(actions).where(
                actions.c.campaign_id == game.store.campaign_id,
                sa.func.json_extract(actions.c.body_json, "$.order_id") == row["id"],
                sa.func.json_extract(actions.c.body_json, "$.play") == "receive_orders",
            )
        )
        .mappings()
        .first()
    )
    if action is None:
        raise WorkflowError("Recover the actual issued Order and source-bound response")
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m2.order_issued",
                sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            )
        )
        .mappings()
        .first()
    )
    if (
        event is None
        or event["actor_id"] != row["issuer_id"]
        or json.loads(event["payload_json"]).get("stim_sex") != meta
        or action["actor_id"] != row["target_id"]
        or action["channel_id"] != row["channel_id"]
    ):
        raise WorkflowError("Recover the immutable actual issued Sex-source Order")
    # The event's frozen state is actual issuance time, not current pharmacology.
    source = _history(c, game, event["id"])
    return bool(
        order_authority(game, c, source, int(row["issuer_id"]), int(row["target_id"])) == meta
    )


class SexService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            targets = []
            from girlframe.engine import m3_bonded as bonded
            from girlframe.services.m3_learned_bonded_stim import parent_lesson
            from girlframe.services.m3_learned_sex import cancelled, lessons

            learned: tuple[dict[str, str], ...] = ()
            try:
                actor = current_ref(state, viewer.user_id)
                learned = lessons(self.game, c, state, actor, rules.RULE)
                own = _native(self.game, c, state, actor)
                cast = _cast(self.game, c, state, channel)
                if (
                    has_rule(state.sheets[actor.entity], rules.RULE, "STIM-BLISSED") or learned
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
                                dict(ref=role.actor.model_dump(mode="json"), label=other.label)
                            )
            except (ValueError, WorkflowError):
                pass
            return dict(
                revision=state.revision,
                lessons=learned,
                targets=targets,
                sessions=[
                    dict(
                        id=x.id,
                        phase="cancelled"
                        if cancelled(
                            self.game, c, state, x.learned_source or parent_lesson(state, x)
                        )
                        else x.phase,
                        caster=x.caster,
                        counterpart=x.counterpart,
                        can_withdraw=x.bonded_source is not None
                        and bonded.get(state, x.bonded_source).changeling_source is None
                        and x.changeling_source is None
                        and x.caster == viewer.user_id
                        and x.action is None
                        and x.phase in ("invited", "accepted"),
                    )
                    for x in rules.records(state, rules.Session)
                    if viewer.user_id in (x.caster, x.counterpart)
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        from girlframe.services.m3_learned_bonded_stim import parent_lesson
        from girlframe.services.m3_learned_sex import cancelled

        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Your actual Stim intimacy and drug source",
                phase="cancelled"
                if cancelled(self.game, c, state, x.learned_source or parent_lesson(state, x))
                else x.phase,
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
                    "Only the actual original participants read this private source"
                )
            for drug in rules.records(state, rules.Drug):
                if drug.session == identity:
                    _drug(self.game, c, state, drug.id)
            for effect in rules.records(state, rules.Effect):
                if effect.action == value.action:
                    prove_effect(self.game, c, state, effect.id)
            from girlframe.services.m3_learned_bonded_stim import parent_lesson
            from girlframe.services.m3_learned_sex import cancelled

            npc_order_effect = None
            if value.target.kind == "npc" and viewer.user_id == value.counterpart:
                from girlframe.services.m3_stim_npc import order_authority as npc_authority

                authority = npc_authority(
                    self.game, c, state, value.target, value.actor, session_id=value.id
                )
                if authority is not None and authority.action == value.action:
                    npc_order_effect = authority.id
            return value.model_dump(mode="json", exclude={"cast", "registry"}) | dict(
                npc_order_effect=npc_order_effect,
                lesson_cancelled=cancelled(
                    self.game, c, state, value.learned_source or parent_lesson(state, value)
                ),
                revision=state.revision,
                drugs=[
                    dict(
                        id=x.id,
                        target=x.target.model_dump(mode="json"),
                        label=x.tag.label,
                        expired=rules.expired(state, x.id),
                    )
                    for x in rules.records(state, rules.Drug)
                    if x.session == identity
                ],
                effects=[
                    dict(
                        kind=x.kind,
                        target=x.target.model_dump(mode="json"),
                        tag=x.tag.label if x.tag else None,
                    )
                    for x in rules.records(state, rules.Effect)
                    if x.action == value.action
                ],
            )

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
            raise WorkflowError("Describe only your actual voluntary source interaction")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected or self.game.pending_actions(c):
                raise WorkflowError("Finish pending Plays and reopen the current source")
            actor = current_ref(state, viewer.user_id)
            own, other = (
                _native(self.game, c, state, actor),
                _counterpart(self.game, c, state, target),
            )
            cast = _cast(self.game, c, state, channel)
            if own.vessel_id is None or other.vessel_id is None:
                raise WorkflowError("Establish the actual original bodies, not imaginary contact")
            approval = self.store.policy.m3_approval
            assert approval is not None
            value = rules.Session(
                id=str(uuid4()),
                actor=actor,
                bonded_source=bonded_source,
                changeling_source=changeling_source,
                target=target,
                caster=viewer.user_id,
                counterpart=other.controller,
                cast=cast,
                registry=approval.registry_sha256,
                actor_vessel=own.vessel_id,
                target_vessel=other.vessel_id,
                proposed_event=str(uuid4()),
                proposal=account,
            )
            if learned_source is not None:
                from girlframe.services.m3_learned_sex import reserve_invitation

                source = reserve_invitation(self.game, c, state, value, rules.RULE, learned_source)
                value = value.model_copy(update=dict(learned_source=source))
            _contact(
                self.game,
                c,
                state,
                value,
                pending_event=value.proposed_event if learned_source else None,
            )
            if not any(x.id == cast.id for x in state.scene_casts):
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
                "m3.stim_sex_invited",
                state,
                event_id=value.proposed_event,
                session=value.id,
            )
            return dict(id=value.id)

        return self.store._write(
            viewer,
            key,
            "m3.stim_sex_invited",
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

    def withdraw(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        """Owner-only unused delegated reservation release; never a fictional refusal."""

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
                or not delegated
                or value.bonded_source is None
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
                        sa.func.json_extract(actions.c.body_json, "$.stim_sex.session") == identity,
                        sa.func.json_extract(actions.c.body_json, "$.prepared.source_work")
                        == identity,
                    ),
                )
            ):
                raise WorkflowError(
                    "Recover the actual original Action; never refund dice or costs"
                )
            event = str(uuid4())
            rules.put(state, value.model_copy(update={"phase": "withdrawn"}))
            if delegated:
                from girlframe.services.m3_learned_bonded_stim import release

                release(self.game, c, state, identity, viewer.user_id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.stim_sex_withdrawn",
                state,
                event_id=event,
                session=identity,
            )
            return dict(id=identity, phase="withdrawn")

        return self.store._write(
            viewer,
            key,
            "m3.stim_sex_withdrawn",
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
        if type(accept) is not bool or not account.strip() or len(account) > 1200:
            raise WorkflowError("Only your own actual source confirmation or decline is accepted")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if (
                value.phase != "invited"
                or viewer.user_id != value.counterpart
                or state.revision != expected
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Answer only your own current original invitation")
            _contact(self.game, c, state, value)
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
                raise WorkflowError("Only the accepting NPC controller records this contact")
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

            record_consent(self.game, c, state, rules.get(state, value.id), accept, event)
            if not accept and value.bonded_source is not None:
                from girlframe.engine import m3_bonded as bonded
                from girlframe.services.m3_learned_bonded_stim import release

                if bonded.get(state, value.bonded_source).changeling_source is None:
                    release(self.game, c, state, identity, viewer.user_id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.stim_sex_consent",
                state,
                event_id=event,
                session=value.id,
            )
            if value.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(self.game, c, state, value.id, event)
            return dict(id=value.id, phase="accepted" if accept else "declined")

        return self.store._write(
            viewer,
            key,
            "m3.stim_sex_consent",
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
