"""Source-owned Alpha Sex subset: actual consent, receipt, Broken, sleep and consequences."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_alpha as broken
from girlframe.engine import m3_alpha_sex as rules
from girlframe.engine import m3_bonded as bonded
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "alpha_sex_damage",
    "alpha_sex_low",
    "alpha_sex_counter_play",
    "alpha_sex_npc_play",
    "alpha_sex_punishment",
    "alpha_sex_wake",
)

COUNTER_PLAYS = (
    "keep_your_head",
    "check_sensors",
    "engage",
    "flirt",
    "disobey_orders",
    "put_someone_beneath_you",
    "all_out_assault",
    "dive_deep",
)


def _copy(state: GameState, changed: GameState) -> None:
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))


def _history(game: GameService, c: Connection, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual original Alpha interaction source")
    return GameState.model_validate_json(raw)


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    access = Access(game.store)
    access.authorize(c, viewer, "plays", director_response=True)
    assert access.registry is not None
    access.registry.require_available(rules.RULE)


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
    from girlframe.services.m3_learned_sex import admit_offer, admit_source

    if (
        sum(x is not None for x in (changeling_source, bonded_source, learned_source, lesson_id))
        > 1
    ):
        raise WorkflowError("Keep actual learned, psychic and Bonded sources separate")
    learned = (
        admit_source(
            game, c, state, actor, target, rules.RULE, learned_source, pending_event=pending_event
        )
        if learned_source is not None
        else admit_offer(game, c, state, actor, rules.RULE, lesson_id)
    )
    remote = admit_contact(game, c, state, actor, target, rules.RULE, changeling_source)

    bound = profiles(c, game.store.campaign_id)
    own, other = resolve(state, actor, bound), resolve(state, target, bound)
    cast = _cast(game, c, state, channel)
    npc = target.kind == "npc"
    if npc:
        from girlframe.services.m3_oldgen_sex import _counterpart, _npc_space

        _counterpart(game, c, state, target)
        _npc_space(game, c, state, other)
        if bonded_source is not None or changeling_source is not None:
            raise WorkflowError("Keep NPC Alpha independent of delegated or psychic sources")
    if (
        actor.kind != "pilot"
        or cast.adjudicator is not None
        or own.offstage_source is not None
        or other.offstage_source is not None
        or own.custody not in (None, "free")
        or other.custody not in (None, "free")
        or target.kind not in ("pilot", "npc")
        or actor == target
        or not (
            (learned or has_rule(state.sheets[actor.entity], rules.RULE, "ALPHA"))
            if bonded_source is None
            else admit_delegation(game, c, state, actor, target, rules.RULE, bonded_source)
        )
        or not any(x.actor == actor and x.controller == own.controller for x in cast.roles)
        or not any(x.actor == target and x.controller == other.controller for x in cast.roles)
        or (not remote and own.inside_frame is not False)
        or (not npc and not remote and other.inside_frame is not False)
        or state.sheets[actor.entity].medical_state != "fit"
        or (not npc and state.sheets[target.entity].medical_state != "fit")
        or is_helpless(state, actor)
        or is_helpless(state, target)
        or (
            not remote
            and own.cell is not None
            and other.cell is not None
            and own.cell != other.cell
        )
        or (not npc and not any(x.family == "girl" and not x.damaged for x in other.assets))
    ):
        raise WorkflowError(
            "Choose distinct capable original Girls with actual contact and an intact Girl Asset"
        )
    rules.require_awake(state, actor)
    rules.require_awake(state, target)


def _npc_current(game: GameService, c: Connection, state: GameState, value: rules.Session) -> None:
    if value.target.kind != "npc":
        return
    from girlframe.services.m3_alpha_npc import contact
    from girlframe.services.m3_oldgen_sex import _counterpart

    own = resolve(state, value.actor, profiles(c, game.store.campaign_id))
    other = _counterpart(game, c, state, value.target)
    if (
        own.vessel_id != value.actor_vessel
        or other.vessel_id != value.target_vessel
        or other.controller != value.counterpart
    ):
        raise WorkflowError("Preserve original NPC controller and actual source bodies")
    contact(game, c, state, value, own, other)


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
            raise WorkflowError("Preserve the exact actual learned Alpha source")
    original = rules.get(_history(game, c, value.proposed_event), identity)
    from girlframe.services.m3_bonded import prove_delegation
    from girlframe.services.m3_learned_bonded_alpha import released_parent

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
        "proposed_event",
        "proposal",
        "bonded_source",
        "changeling_source",
        "learned_source",
        "actor_vessel",
        "target_vessel",
    )
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.proposed_event,
        )
    ).first()
    if (
        any(getattr(value, x) != getattr(original, x) for x in stable)
        or audit is None
        or audit.kind != "m3.alpha_sex_invited"
        or audit.actor_id != str(value.caster)
    ):
        raise WorkflowError("Recover the actual original source proposal and controllers")
    if value.consent_event:
        consent = rules.get(_history(game, c, value.consent_event), identity)
        response = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.consent_event,
            )
        ).first()
        if (
            response is None
            or response.kind != "m3.alpha_sex_consent"
            or response.actor_id != str(value.counterpart)
            or consent.npc_contact != value.npc_contact
            or consent.consent_account != value.consent_account
            or consent.phase not in ("accepted", "declined")
            or consent.actor != value.actor
            or consent.target != value.target
        ):
            raise WorkflowError(
                "Only the actual counterpart's source answer establishes this interaction"
            )
    if value.npc_contact is not None:
        from girlframe.services.m3_alpha_npc import _prove_npc_contact

        _prove_npc_contact(game, c, value)
    if value.effect_event:
        effect_state = _history(game, c, value.effect_event)
        effect = rules.get(effect_state, value.id)
        actual = game.action(c, value.action or "")
        receipt = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == value.action,
            )
        )
        if (
            effect.action != value.action
            or effect.effect_event != value.effect_event
            or effect.condition != value.condition
            or effect.sleep_event != value.sleep_event
            or actual["data"].get("play") != rules.PLAY
            or actual["data"].get("alpha_sex", {}).get("session") != value.id
            or receipt is None
            or json.loads(receipt) != actual["data"].get("receipt")
        ):
            raise WorkflowError("Recover the actual rolled source before using its effects")
        if value.target.kind == "npc" and actual["data"]["result"]["tier"] == "high":
            death = dict(
                kind="alpha_sex_npc_death",
                event=value.effect_event,
                action=value.action,
                session=value.id,
                target=value.target.model_dump_json(),
            )
            if (
                death not in effect_state.facts
                or death not in state.facts
                or not actual["data"]["result"].get("npc_killed")
                or effect_state.world is None
                or not any(
                    x.id == value.target.entity and not x.alive for x in effect_state.world.npcs
                )
            ):
                raise WorkflowError(
                    "Recover the actual source-owned NPC death, never an Asset substitute"
                )
    if value.npc_performance is not None:
        from girlframe.services.m3_alpha_npc import prove_performance

        prove_performance(game, c, state, value)
    return value


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    state = load_state(c, game.store.campaign_id)
    meta = action["data"]["alpha_sex"]
    value = prove(game, c, state, meta["session"])
    approval = game.store.policy.m3_approval
    if (
        approval is None
        or value.registry != approval.registry_sha256
        or value.action != action["id"]
        or not value.consent_event
        or value.phase == "declined"
        or viewer.user_id not in meta["table"]
        or fingerprint(_cast(game, c, state, int(action["channel_id"]))) != fingerprint(value.cast)
    ):
        raise WorkflowError("Recover the actual accepted original source interaction and table")
    resolve(state, value.actor, profiles(c, game.store.campaign_id))
    resolve(state, value.target, profiles(c, game.store.campaign_id))


def preview(game: GameService, viewer: GuildViewer, channel: int) -> dict[str, Any]:
    try:
        with game.store.engine.connect() as c:
            _access(game, c, viewer)
            state = load_state(c, game.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            ready = []
            for value in rules.sessions(state):
                if (
                    value.actor != actor
                    or value.phase != "accepted"
                    or value.cast.channel != channel
                ):
                    continue
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
                prove(game, c, state, value.id)
                ready.append(
                    dict(
                        id=value.id,
                        ref=value.target.model_dump(mode="json"),
                        label=resolve(
                            state, value.target, profiles(c, game.store.campaign_id)
                        ).label,
                    )
                )
            return dict(available=bool(ready), sessions=ready)
    except (WorkflowError, ValueError):
        return dict(available=False, sessions=[])


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
        raise WorkflowError("Use this actual accepted voluntary source and original counterpart")
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
    _npc_current(game, c, state, value)
    if fingerprint(_cast(game, c, state, channel)) != fingerprint(value.cast):
        raise WorkflowError(
            "The accepted source cast changed; establish the actual interaction again"
        )
    from girlframe.services.m3_learned_bonded_alpha import parent_lesson

    delegated_lesson = parent_lesson(state, value)
    return (
        dict(
            session=value.id,
            actor=value.actor.model_dump(mode="json"),
            target=value.target.model_dump(mode="json"),
            cast=value.cast.model_dump(mode="json"),
            cast_sha256=fingerprint(value.cast),
            table=sorted(
                {x.controller for x in value.cast.roles}
                | ({value.cast.facilitator} if value.cast.facilitator is not None else set())
            ),
            caster=value.caster,
            counterpart=value.counterpart,
            phase="unrolled",
            followups=[],
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


def bind(state: GameState, action: dict[str, Any]) -> None:
    value = rules.get(state, action["data"]["alpha_sex"]["session"])
    if value.phase != "accepted" or value.action is not None:
        raise WorkflowError("This accepted interaction already has its actual Play")
    rules.put(state, value.model_copy(update=dict(action=action["id"], phase="active")))


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    value = rules.get(state, action["data"]["alpha_sex"]["session"])
    _contact(
        game,
        c,
        state,
        value.actor,
        value.target,
        int(action["channel_id"]),
        bonded_source=value.bonded_source,
        changeling_source=value.changeling_source,
        learned_source=value.learned_source,
    )
    _npc_current(game, c, state, value)
    if value.effect_event:
        raise WorkflowError("Resume the actual saved source result; do not reroll")


def _finish(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if game.pending(c, action["id"]) or action["state"] == "complete":
        return
    from girlframe.services.m2_choices import ChoiceEngine

    value = rules.get(state, action["data"]["alpha_sex"]["session"])
    rules.put(state, value.model_copy(update={"phase": "complete"}))
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["alpha_sex"]
    value = rules.get(state, meta["session"])
    if value.effect_event:
        raise WorkflowError("Resume this original source result")
    event = action["data"]["response_event"]
    level = action["data"]["result"]["tier"]
    from girlframe.services.m3_gender_designation import offer_animal_tags

    if offer_animal_tags(game, c, state, action):
        action["data"]["gender_sex_deferred"] = True
        return
    value = value.model_copy(update={"effect_event": event})
    if level == "low":
        value = value.model_copy(update={"sleep_event": event, "phase": "sleeping"})
        rules.put(state, value)
        meta["phase"] = "opportunity"
        game.request(c, action, value.counterpart, "alpha_sex_low")
        return
    _copy(state, change(state, value.actor, value.target, 1, event))
    _copy(
        state,
        broken.inflict(state, value.target, value.actor, action["id"], event, distinct_source=True),
    )
    condition = next(
        x
        for x in broken.conditions(state, value.target, value.actor)
        if x.source_action == action["id"]
    )
    value = value.model_copy(update={"condition": condition.id})
    rules.put(state, value)
    meta["phase"] = "effects"
    action["data"]["result"].update(bond_deepened=True, broken=True, scent_tracking=True)
    if level == "high" and value.target.kind == "npc":
        from girlframe.engine.m3_battle import end_actor_casts
        from girlframe.engine.m3_physical import interrupt_journeys

        _npc_current(game, c, state, value)
        assert state.world is not None
        npc = next(x for x in state.world.npcs if x.id == value.target.entity and x.alive)
        _copy(state, interrupt_journeys(state, value.target, event, "Actual Alpha source death"))
        _copy(state, end_actor_casts(state, value.target, event))
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"alive": False}) if x.id == npc.id else x
                    for x in state.world.npcs
                )
            }
        )
        state.facts.append(
            dict(
                kind="alpha_sex_npc_death",
                event=event,
                action=action["id"],
                session=value.id,
                target=value.target.model_dump_json(),
            )
        )
        action["data"]["result"].update(npc_killed=True)
        _finish(game, c, state, action)
    elif level == "high":
        game.request(c, action, value.caster, "alpha_sex_damage")
    else:
        _finish(game, c, state, action)


def _wake(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.get(state, action["data"]["alpha_sex"]["session"])
    rules.put(state, value.model_copy(update={"phase": "waking"}))
    action["data"]["alpha_sex"]["phase"] = "waking"
    game.request(c, action, value.caster, "alpha_sex_wake")


def _takeable(
    game: GameService, c: Connection, state: GameState, value: rules.Session
) -> list[dict[str, Any]]:
    from girlframe.engine.m3_items import take
    from girlframe.services.m3_items import available_items, new_void_families

    selected = []
    for item in available_items(c, game, state, value.actor):
        try:
            changed = take(
                state,
                value.actor,
                value.target,
                profiles(c, game.store.campaign_id),
                item["id"],
                value.action or value.id,
                "preview-not-committed",
                "Actual source opportunity",
                origin_event=value.effect_event or value.proposed_event,
                inside_frame=False,
            )
            if not new_void_families(state, changed):
                selected.append(item)
        except ValueError:
            continue
    return selected


def projection(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    value = rules.get(state, action["data"]["alpha_sex"]["session"])
    from girlframe.services.m3_alpha_npc import plays
    from girlframe.services.m3_role_punishments import supported

    npc_plays = plays(game, state, value) if not is_helpless(state, value.target) else []
    return dict(
        assets=[
            dict(id=x.id, label=x.name if not x.concealed else "Undisclosed Girl Asset")
            for x in resolve(state, value.target, profiles(c, game.store.campaign_id)).assets
            if x.family == "girl" and not x.damaged
        ],
        items=_takeable(game, c, state, value) if request["kind"] == "alpha_sex_low" else [],
        can_counter=value.target.kind == "pilot" and not is_helpless(state, value.target),
        npc_plays=npc_plays,
        npc_counter_unsupported=value.target.kind == "npc" and not npc_plays,
        can_punish=supported(state, value.actor, value.target, profiles(c, game.store.campaign_id)),
        session=value.id,
        asleep=rules.asleep(state, value.actor),
    )


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    meta = action["data"]["alpha_sex"]
    value = rules.get(state, meta["session"])
    event = action["data"]["response_event"]
    _npc_current(game, c, state, value)
    if (
        answer.denied
        or answer.number is not None
        or answer.member is not None
        or answer.flag is not None
    ):
        raise WorkflowError("Use only this actual owned Alpha outcome")
    if request["kind"] == "alpha_sex_damage":
        if answer.fields or answer.text or len(answer.options) != 1:
            raise WorkflowError("Choose exactly one actual intact Girl Asset")
        from girlframe.services.m3_battle import damage_actor

        changed, work = damage_actor(
            game,
            c,
            state,
            target=value.target,
            asset_id=answer.options[0],
            source_action=action["id"],
            source_work=None,
            event=event,
            actor=value.actor,
            opponent=value.actor,
            chooser_controller=value.caster,
            occurrence="alpha_sex",
            physical_blow=True,
        )
        _copy(state, changed)
        meta["followups"].extend(work)
        meta["damage_event"] = event
    elif request["kind"] == "alpha_sex_low":
        if len(answer.options) != 1 or answer.options[0] not in ("pass", "take", "play", "punish"):
            raise WorkflowError("Choose your actual one opportunity")
        choice = answer.options[0]
        if choice != "take" and (answer.fields or answer.text):
            raise WorkflowError("Use only the selected actual opportunity")
        meta.update(opportunity=choice, selection_choice=request["id"], selection_event=event)
        if choice == "pass":
            _wake(game, c, state, action)
        elif choice == "take":
            if set(answer.fields) != {"item"} or not answer.text.strip():
                raise WorkflowError("Choose the actual held object and describe taking it")
            if answer.fields["item"] not in {x["id"] for x in _takeable(game, c, state, value)}:
                raise WorkflowError(
                    "This exact source object needs its supported inventory/Void port"
                )
            game.save_action(c, action)
            from girlframe.services.m3_items import take_in_transaction

            _copy(
                state,
                take_in_transaction(
                    c,
                    game,
                    state,
                    source=value.actor,
                    recipient=value.target,
                    selection=answer.fields["item"],
                    action=action["id"],
                    event=event,
                    account=answer.text,
                    inside_frame=False,
                ),
            )
            _wake(game, c, state, action)
        elif choice == "play":
            if is_helpless(state, value.target):
                raise WorkflowError("The actual counterpart cannot make an ordinary counter")
            if value.target.kind == "npc":
                from girlframe.services.m3_alpha_npc import plays

                if not plays(game, state, value):
                    raise WorkflowError(
                        "NPC performer needs a supported job-defined Conversation Play; "
                        "opportunity remains pending"
                    )
                meta["phase"] = "npc_play"
                game.request(c, action, value.counterpart, "alpha_sex_npc_play")
            else:
                meta["phase"] = "counter"
                game.request(c, action, value.counterpart, "alpha_sex_counter_play")
        else:
            from girlframe.services.m3_role_punishments import open_case

            changed, case = open_case(
                state,
                profiles(c, game.store.campaign_id),
                actor=value.target,
                target=value.actor,
                chooser=value.target,
                source_kind="alpha_sex",
                action=action["id"],
                source_event=event,
                identity=str(uuid4()),
                source_work=value.id,
                chooser_controller=value.counterpart,
                executor_controller=value.counterpart,
            )
            _copy(state, changed)
            rules.put(state, value.model_copy(update={"case": case}))
            meta.update(phase="punishment", case=case)
            game.request(c, action, value.counterpart, "alpha_sex_punishment", dict(case=case))
    elif request["kind"] == "alpha_sex_npc_play":
        from girlframe.services.m3_alpha_npc import perform

        performance = perform(game, c, state, value, action, request, answer)
        rules.put(state, value.model_copy(update={"npc_performance": performance}))
        meta["npc_performance"] = performance.id
        _wake(game, c, state, action)
    elif request["kind"] == "alpha_sex_wake":
        if answer.options != ("wake",) or answer.fields or not answer.text.strip():
            raise WorkflowError("The original Alpha records actually waking from this source sleep")
        rules.put(state, value.model_copy(update={"wake_event": event, "phase": "complete"}))
        meta["phase"] = "effects"
    else:
        raise WorkflowError(
            "Complete the actual source Play or Punishment; do not acknowledge it away"
        )


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    meta = action["data"]["alpha_sex"]
    if meta.get("damage_event") and not meta.get("materialized"):
        from girlframe.services.m3_battle import synchronize_damage

        synchronize_damage(game, c, event)
        latest = game.action(c, action["id"])
        action.clear()
        action.update(latest)
        action["data"]["alpha_sex"]["materialized"] = event
    if meta.get("case"):
        from girlframe.services.m3_role_punishments import synchronize as sync_role

        sync_role(game, c, None, event)
    if action["data"]["alpha_sex"]["phase"] == "effects":
        state = load_state(c, game.store.campaign_id)
        before = state.model_dump_json()
        _finish(game, c, state, action)
        if state.model_dump_json() != before:
            audit = c.execute(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            ).scalar_one()
            completed = game.event(
                c, audit, str(uuid4()), "m3.alpha_sex_completed", state, action_id=action["id"]
            )
            value = rules.get(state, action["data"]["alpha_sex"]["session"])
            if value.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(game, c, state, value.id, completed)
    game.save_action(c, action)
    # High-result damage may finish here, after the general response hook checked
    # the parent. Preserve the native consequences before completing its real link.
    from girlframe.services.m3_bonded import synchronize_delegation

    synchronize_delegation(game, c, game.action(c, action["id"]), event)


def validate_transfer_source(
    c: Connection,
    game: GameService,
    state: GameState,
    action: dict[str, Any],
    source_actor: ActorRef,
    recipient: ActorRef,
) -> None:
    value = prove(game, c, state, action["data"]["alpha_sex"]["session"])
    if (
        value.actor != source_actor
        or value.target != recipient
        or not rules.asleep(state, value.actor)
        or action["data"]["alpha_sex"].get("opportunity") != "take"
    ):
        raise WorkflowError(
            "Only this original sleeping source's actual counterpart takes its object"
        )


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    if case.action is None:
        raise WorkflowError("Use the actual rolled Alpha opportunity")
    action = game.action(c, case.action)
    value = prove(game, c, state, case.source_work or "")
    _npc_current(game, c, state, value)
    from girlframe.services.m3_intracadre_marriage import original_offender

    offender = original_offender(game, c, state, case.id, case.source_event, case.subject)
    if (
        value.action != case.action
        or value.case != case.id
        or case.executor != value.target
        or case.chooser != value.target
        or offender != value.actor
        or case.chooser_controller != value.counterpart
        or case.executor_controller != value.counterpart
        or offender == case.subject
        and case.subject_controller != value.caster
        or action["data"]["result"]["tier"] != "low"
        or action["data"]["alpha_sex"].get("case") != case.id
    ):
        raise WorkflowError("Preserve the actual original low-result Punishment grant")
    original = rules.get(_history(game, c, case.source_event), value.id)
    if original.case != case.id or not original.sleep_event:
        raise WorkflowError("Recover the actual counterpart's source-selected Punishment")


def complete_role_case(c: Connection, game: GameService, case: Any, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    if not case.completion_event:
        raise WorkflowError("Only a real completed Punishment resolves this opportunity")
    action = game.action(c, case.action)
    _close_required(game, c, action, "alpha_sex_punishment")
    _wake(game, c, state, action)
    game.save_action(c, action)
    game.event(
        c,
        case.executor_controller,
        str(uuid4()),
        "m3.alpha_sex_opportunity_completed",
        state,
        action_id=action["id"],
        source_event=event,
    )


def _close_required(game: GameService, c: Connection, action: dict[str, Any], kind: str) -> None:
    rows = [x for x in game.pending(c, action["id"]) if x["kind"] == kind]
    if len(rows) != 1:
        raise WorkflowError("Recover this exact original required opportunity")
    table = t.m2["m2_choices"]
    c.execute(
        table.update()
        .where(table.c.campaign_id == game.store.campaign_id, table.c.id == rows[0]["id"])
        .values(state="completed_by_work", revision=rows[0]["revision"] + 1)
    )


def counter_plays(
    game: GameService, c: Connection, state: GameState, parent: dict[str, Any], actor: ActorRef
) -> tuple[str, ...]:
    """Offer only these native own recipes with their actual source conditions."""
    from girlframe.engine import m3_dose_up as dose
    from girlframe.engine import m3_oldgen as oldgen
    from girlframe.services.m3_access import load_registry
    from girlframe.services.m3_dose_up import _native, _operator

    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        return COUNTER_PLAYS
    extra = []
    try:
        _counter_scope(game, c, state, parent, actor)
        if sheet.girl == "STIM-BLISSED" and has_rule(sheet, dose.RULE, "STIM-BLISSED"):
            _operator(game, c, state, actor)
            load_registry().require_available(dose.RULE)
            extra.append(dose.PLAY)
        elif sheet.girl == "OLDGEN" and has_rule(sheet, oldgen.ADVICE, "OLDGEN"):
            _native(game, c, state, actor)
            load_registry().require_available(oldgen.ADVICE)
            for role in _cast(game, c, state, int(parent["channel_id"])).roles:
                if (
                    role.actor.kind != "pilot"
                    or role.actor == actor
                    or rules.asleep(state, role.actor)
                ):
                    continue
                try:
                    _native(game, c, state, role.actor)
                except (ValueError, WorkflowError):
                    continue
                extra.append(oldgen.PLAY)
                break
    except (ValueError, WorkflowError):
        return COUNTER_PLAYS
    if doll_observers(game, c, state, parent, actor):
        extra.append("unassuming_doll")
    return (*COUNTER_PLAYS, *extra)


def _counter_scope(
    game: GameService, c: Connection, state: GameState, parent: dict[str, Any], actor: ActorRef
) -> dict[str, Any]:
    actual = game.action(c, parent["id"])
    meta = actual["data"].get("alpha_sex")
    if meta is None:
        raise WorkflowError("Use the actual original Alpha sleeping-source parent")
    value = prove(game, c, state, meta["session"])
    row = next(
        (x for x in game.pending(c, actual["id"]) if x["kind"] == "alpha_sex_counter_play"), None
    )
    selection = (
        c.execute(
            sa.select(t.m2["m2_responses"]).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == meta.get("selection_choice"),
                t.m2["m2_responses"].c.event_id == meta.get("selection_event"),
                t.m2["m2_responses"].c.actor_id == str(value.counterpart),
            )
        )
        .mappings()
        .first()
    )
    if (
        value.action != actual["id"]
        or value.target != actor
        or actor.kind != "pilot"
        or value.target != current_ref(state, value.counterpart)
        or meta.get("phase") != "counter"
        or value.phase != "sleeping"
        or not rules.asleep(state, value.actor)
        or value.wake_event
        or row is None
        or row["actor_id"] != str(value.counterpart)
        or selection is None
        or ChoiceAnswer.model_validate_json(selection["answer_json"]).options != ("play",)
    ):
        raise WorkflowError("Preserve the original counterpart's actual selected sleeping counter")
    cast = _cast(game, c, state, value.cast.channel)
    if fingerprint(cast) != fingerprint(value.cast):
        raise WorkflowError("Preserve the actual original counter source scene and people")
    return dict(parent=actual["id"], choice=row["id"], actor=actor.model_dump(mode="json"))


def doll_observers(
    game: GameService, c: Connection, state: GameState, parent: dict[str, Any], actor: ActorRef
) -> tuple[dict[str, Any], ...]:
    """Actual awake observers for the native Doll's original sleeping opportunity."""
    from girlframe.engine import m3_vatgrown as doll
    from girlframe.services.m3_access import load_registry
    from girlframe.services.m3_vatgrown import _context

    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.girl != "VATGROWN" or not has_rule(sheet, doll.RULE, "VATGROWN"):
        return ()
    try:
        _counter_scope(game, c, state, parent, actor)
        load_registry().require_available(doll.RULE)
    except (ValueError, WorkflowError):
        return ()
    result = []
    for role in _cast(game, c, state, int(parent["channel_id"])).roles:
        if role.actor == actor or rules.asleep(state, role.actor) or is_helpless(state, role.actor):
            continue
        try:
            _context(
                game, c, state.model_copy(deep=True), actor, role.actor, int(parent["channel_id"])
            )
            resolved = resolve(state, role.actor, profiles(c, game.store.campaign_id))
        except (ValueError, WorkflowError):
            continue
        result.append(
            dict(id=role.actor.token, ref=role.actor.model_dump(mode="json"), label=resolved.label)
        )
    return tuple(result)


def doll_counter(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    prepared: PlayInput,
    channel: int,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from girlframe.engine import m3_vatgrown as doll

    if prepared.play != doll.PLAY or prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    if not parent["data"].get("alpha_sex"):
        return None
    scope = _counter_scope(game, c, state, parent, actor)
    observers = doll_observers(game, c, state, parent, actor)
    if (
        prepared.target_actor is None
        or prepared.target_actor.model_dump(mode="json") not in [x["ref"] for x in observers]
        or prepared.target is not None
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or not prepared.trigger_confirmed
        or is_helpless(state, actor)
        or rules.asleep(state, actor)
        or channel != int(parent["channel_id"])
    ):
        raise WorkflowError(
            "Use the original native Doll and an actual awake observer in this opportunity"
        )
    if action is not None and (
        action["data"].get("alpha_sex_counter_source") != scope
        or action["parent_id"] != parent["id"]
        or action["actor_id"] != actor.entity
        or action["data"]["prepared"] != prepared.model_dump(mode="json")
    ):
        raise WorkflowError("Recover this exact original Doll counter before rolling")
    return scope


def self_dose_counter(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    prepared: PlayInput,
    channel: int,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """An actual self Play in the real counter slot; no separate recipe/foreign contact."""
    from girlframe.engine import m3_dose_up as dose
    from girlframe.services.m3_dose_up import _operator

    if prepared.play != dose.PLAY or prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    if not parent["data"].get("alpha_sex"):
        return None
    actor = current_ref(state, viewer.user_id)
    scope = _counter_scope(game, c, state, parent, actor)
    if (
        dose.PLAY not in counter_plays(game, c, state, parent, actor)
        or prepared.source_work is not None
        or prepared.target is not None
        or prepared.target_actor not in (None, actor)
        or prepared.order_id
        or prepared.off_duty_id
        or is_helpless(state, actor)
        or int(parent["channel_id"]) != channel
    ):
        raise WorkflowError("Use the actual native Stim's owned self-Dose in this original counter")
    _operator(game, c, state, actor)
    if action is not None and (
        action["data"].get("alpha_sex_counter_source") != scope
        or action["parent_id"] != parent["id"]
        or action["actor_id"] != actor.entity
        or action["data"]["prepared"] != prepared.model_dump(mode="json")
    ):
        raise WorkflowError("Recover this exact original self-Dose counter Action before rolling")
    return scope


def advice_counter(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    prepared: PlayInput,
    channel: int,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Real Oldgen advice to an awake original person, not speech for the sleeper."""
    from girlframe.engine import m3_oldgen as oldgen
    from girlframe.services.m3_dose_up import _native

    if prepared.play != oldgen.PLAY or prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    if not parent["data"].get("alpha_sex"):
        return None
    scope = _counter_scope(game, c, state, parent, actor)
    if (
        oldgen.PLAY not in counter_plays(game, c, state, parent, actor)
        or prepared.source_work is not None
        or prepared.target is None
        or prepared.target == int(actor.entity)
        or prepared.target_actor is not None
        or prepared.order_id
        or prepared.off_duty_id
        or is_helpless(state, actor)
        or int(parent["channel_id"]) != channel
    ):
        raise WorkflowError("Use the actual native Oldgen's own advice in her original counter")
    target = current_ref(state, prepared.target)
    if rules.asleep(state, target) or not any(
        role.actor == target and role.controller == prepared.target
        for role in _cast(game, c, state, channel).roles
    ):
        raise WorkflowError("Advise an actual awake original Girl in this counter's scene")
    _native(game, c, state, target)
    if action is not None and (
        action["data"].get("alpha_sex_counter_source") != scope
        or action["parent_id"] != parent["id"]
        or action["actor_id"] != actor.entity
        or action["data"]["prepared"] != prepared.model_dump(mode="json")
    ):
        raise WorkflowError("Recover this exact original advice counter Action before rolling")
    return scope


def validate_counter_child(
    game: GameService, c: Connection, parent: dict[str, Any], actor: ActorRef, prepared: PlayInput
) -> dict[str, Any]:
    state = load_state(c, game.store.campaign_id)
    if prepared.play == "unassuming_doll":
        scope = doll_counter(game, c, state, actor, prepared, int(parent["channel_id"]))
        if scope is None or scope["parent"] != parent["id"]:
            raise WorkflowError("Recover this original Doll counter's sleeping parent")
        return scope
    if prepared.play == "old_dog_new_pups":
        scope = advice_counter(game, c, state, actor, prepared, int(parent["channel_id"]))
        if scope is None or scope["parent"] != parent["id"]:
            raise WorkflowError("Recover this original Oldgen counter's sleeping parent")
        return scope
    if prepared.play == "dose_up":
        from girlframe.engine import m3_dose_up as dose
        from girlframe.services.m3_dose_up import _operator

        scope = _counter_scope(game, c, state, parent, actor)
        if (
            prepared.parent != parent["id"]
            or prepared.source_work is not None
            or prepared.target is not None
            or prepared.target_actor not in (None, actor)
            or prepared.order_id
            or prepared.off_duty_id
            or dose.PLAY not in counter_plays(game, c, state, parent, actor)
        ):
            raise WorkflowError("Use the actual native Stim self-Dose counter, not another recipe")
        _operator(game, c, state, actor)
        return scope
    value = rules.get(state, parent["data"]["alpha_sex"]["session"])
    row = next(
        (x for x in game.pending(c, parent["id"]) if x["kind"] == "alpha_sex_counter_play"), None
    )
    if (
        row is None
        or actor != value.target
        or prepared.play not in COUNTER_PLAYS
        or prepared.parent != parent["id"]
        or prepared.source_work
        or value.phase != "sleeping"
    ):
        raise WorkflowError("Use this actual counterpart's genuine ordinary counter Play")
    return dict(parent=parent["id"], choice=row["id"], actor=value.target.model_dump(mode="json"))


def synchronize_counters(game: GameService, c: Connection, event: str) -> GameState | None:
    table = t.m2["m2_actions"]
    identities = c.scalars(
        sa.select(table.c.id).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.state == "complete",
            sa.func.json_extract(table.c.body_json, "$.alpha_sex_counter_source").is_not(None),
            sa.func.json_extract(table.c.body_json, "$.alpha_sex_counter_done").is_(None),
        )
    ).all()
    for identity in identities:
        child = game.action(c, identity)
        source = child["data"]["alpha_sex_counter_source"]
        parent = game.action(c, source["parent"])
        state = load_state(c, game.store.campaign_id)
        value = prove(game, c, state, parent["data"]["alpha_sex"]["session"])
        receipt = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == identity,
            )
        )
        selection = c.scalar(
            sa.select(t.m2["m2_responses"].c.answer_json).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == parent["data"]["alpha_sex"]["selection_choice"],
                t.m2["m2_responses"].c.event_id == parent["data"]["alpha_sex"]["selection_event"],
                t.m2["m2_responses"].c.actor_id == str(value.counterpart),
            )
        )
        if child["data"]["play"] == "unassuming_doll":
            from girlframe.engine import m3_vatgrown as doll
            from girlframe.services.m3_vatgrown import prove as prove_doll

            original = doll.source(state, identity)
            # The choice event is saved before its response row. Only defer that
            # exact in-flight response; the post-response callback proves it fully.
            if (
                original.completed_event == event
                and c.scalar(
                    sa.select(t.m2["m2_responses"].c.event_id).where(
                        t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_responses"].c.event_id == event,
                    )
                )
                is None
            ):
                incoming = (
                    c.execute(
                        sa.select(t.events).where(
                            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                        )
                    )
                    .mappings()
                    .one()
                )
                payload = json.loads(incoming["payload_json"])
                pending_response = (
                    c.execute(
                        sa.select(t.m2["m2_choices"]).where(
                            t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                            t.m2["m2_choices"].c.id == payload.get("choice_id"),
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    incoming["kind"] != "m3.choice_resolved"
                    or payload.get("action_id") != identity
                    or pending_response is None
                    or pending_response["action_id"] != identity
                    or pending_response["kind"] not in ("vat_doll_benefits", "vat_doll_information")
                    or incoming["actor_id"] != pending_response["actor_id"]
                ):
                    raise WorkflowError("Recover the exact current Doll response event")
                continue
            proved = prove_doll(game, c, state, identity)
            if (
                not proved.complete
                or proved.actor != value.target
                or proved.target == value.actor
                or proved.cast != value.cast
                or child["data"].get("learned_play")
                or child["data"]["vatgrown"].get("princess_direction")
                or source != _counter_scope(game, c, state, parent, value.target)
            ):
                raise WorkflowError(
                    "Complete the actual original Doll and its mandatory consequences"
                )
        if child["data"]["play"] == "old_dog_new_pups":
            from girlframe.engine import m3_oldgen as oldgen
            from girlframe.services.m3_oldgen import prove_advice

            advice = oldgen.records(state, oldgen.Advice)
            advice_source = next((x for x in advice if x.id == identity), None)
            meta = child["data"].get("oldgen", {})
            if advice_source is None or meta.get("phase") != "complete":
                raise WorkflowError("Complete the actual original advice and owned listening")
            # The current choice event precedes its immutable SQL response insert.
            # Defer only that exact event; respond calls us again after insertion.
            choice = meta.get("listen_choice") if advice_source.total >= 8 else advice_source.choice
            response_event = (
                meta.get("listen_event") if advice_source.total >= 8 else advice_source.event
            )
            chooser = advice_source.counterpart
            response = c.scalar(
                sa.select(t.m2["m2_responses"].c.event_id).where(
                    t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_responses"].c.choice_id == choice,
                )
            )
            if response is None:
                incoming = (
                    c.execute(
                        sa.select(t.events).where(
                            t.events.c.campaign_id == game.store.campaign_id,
                            t.events.c.id == event,
                        )
                    )
                    .mappings()
                    .one()
                )
                payload = json.loads(incoming["payload_json"])
                if (
                    response_event != event
                    or incoming["kind"] != "m3.choice_resolved"
                    or incoming["actor_id"] != str(chooser)
                    or payload.get("action_id") != identity
                    or payload.get("choice_id") != choice
                ):
                    raise WorkflowError("Recover the exact current advice response event")
                continue
            advice_proved = prove_advice(game, c, state, identity)
            if (
                advice_proved.actor != value.target
                or advice_proved.target == value.actor
                or rules.asleep(state, advice_proved.target)
                or advice_proved.cast != value.cast
                or child["data"].get("learned_play")
                or child["data"]["prepared"].get("source_work") is not None
                or source != _counter_scope(game, c, state, parent, value.target)
            ):
                raise WorkflowError("Preserve this native Oldgen's original source and recipient")
        if child["data"]["play"] == "dose_up":
            from girlframe.services.m3_dose_up import prove as prove_dose

            # Game.event publishes the canonical choice event before respond inserts
            # its response row. Defer only that exact current selection; the
            # post-response callback must prove the complete actual Dose below.
            staged = next(
                (x for x in child["data"]["dose_up"]["selections"] if x["event"] == event),
                None,
            )
            if staged is not None:
                response = c.scalar(
                    sa.select(t.m2["m2_responses"].c.event_id).where(
                        t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_responses"].c.choice_id == staged["choice"],
                    )
                )
                if response is None:
                    incoming = (
                        c.execute(
                            sa.select(t.events).where(
                                t.events.c.campaign_id == game.store.campaign_id,
                                t.events.c.id == event,
                            )
                        )
                        .mappings()
                        .one()
                    )
                    payload = json.loads(incoming["payload_json"])
                    if (
                        incoming["kind"] != "m3.choice_resolved"
                        or incoming["actor_id"] != str(staged["chooser"])
                        or payload.get("action_id") != child["id"]
                        or payload.get("choice_id") != staged["choice"]
                    ):
                        raise WorkflowError("Recover the exact current Dose response event")
                    continue
            dose = prove_dose(game, c, state, child["id"])
            if (
                dose.actor != value.target
                or dose.target != value.target
                or dose.contact is not None
                or dose.order is not None
                or child["data"]["dose_up"]["phase"] != "complete"
                or child["data"]["prepared"].get("source_work") is not None
                or child["data"]["dose_up"].get("princess_direction") is not None
                or child["data"]["dose_up"].get("required_recipe") is not None
                or source != _counter_scope(game, c, state, parent, value.target)
            ):
                raise WorkflowError("Complete the actual original Stim's genuine self-Dose counter")
        if (
            child["parent_id"] != parent["id"]
            or parent["data"]["alpha_sex"].get("phase") != "counter"
            or selection is None
            or ChoiceAnswer.model_validate_json(selection).options != ("play",)
            or child["actor_id"] != value.target.entity
            or child["data"]["play"]
            not in (*COUNTER_PLAYS, "dose_up", "old_dog_new_pups", "unassuming_doll")
            or child["data"]["character_ids"].get(value.target.entity) != value.target.incarnation
            or receipt is None
            or json.loads(receipt) != child["data"].get("receipt")
            or game.pending(c, identity)
        ):
            raise WorkflowError("Only the genuine completed original counter ends this opportunity")
        _close_required(game, c, parent, "alpha_sex_counter_play")
        _wake(game, c, state, parent)
        child["data"]["alpha_sex_counter_done"] = event
        game.save_action(c, child)
        game.save_action(c, parent)
        actor = c.execute(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        ).scalar_one()
        game.event(
            c,
            actor,
            str(uuid4()),
            "m3.alpha_sex_counter_completed",
            state,
            action_id=parent["id"],
            source_event=event,
        )
    return load_state(c, game.store.campaign_id) if identities else None


class SexService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            actor = (
                current_ref(state, viewer.user_id) if str(viewer.user_id) in state.sheets else None
            )
            from girlframe.services.m3_learned_bonded_alpha import parent_lesson
            from girlframe.services.m3_learned_sex import cancelled, lessons

            offered = lessons(self.game, c, state, actor, rules.RULE) if actor is not None else ()
            targets = []
            if actor is not None and (
                has_rule(state.sheets[actor.entity], rules.RULE, "ALPHA") or offered
            ):
                for role in cast.roles:
                    if role.actor.kind not in ("pilot", "npc") or role.actor == actor:
                        continue
                    try:
                        _contact(
                            self.game,
                            c,
                            state,
                            actor,
                            role.actor,
                            channel,
                            lesson_id=offered[0]["id"] if offered else None,
                        )
                    except (ValueError, WorkflowError):
                        continue
                    targets.append(
                        dict(
                            ref=role.actor.model_dump(mode="json"),
                            label=resolve(
                                state, role.actor, profiles(c, self.store.campaign_id)
                            ).label,
                        )
                    )
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
                        actor=x.actor.model_dump(mode="json"),
                        target=x.target.model_dump(mode="json"),
                        caster=x.caster,
                        counterpart=x.counterpart,
                        tracking=rules.tracking(state, x),
                        can_withdraw=(
                            x.learned_source is not None
                            or (
                                x.bonded_source is not None
                                and bonded.get(state, x.bonded_source).changeling_source is None
                            )
                        )
                        and x.caster == viewer.user_id
                        and x.action is None
                        and x.phase in ("invited", "accepted"),
                    )
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
                    "Only the actual original participants may read this private source"
                )
            from girlframe.services.m3_learned_bonded_alpha import parent_lesson
            from girlframe.services.m3_learned_sex import cancelled

            ended = cancelled(
                self.game, c, state, value.learned_source or parent_lesson(state, value)
            )
            return dict(
                id=value.id,
                revision=state.revision,
                phase="cancelled" if ended else value.phase,
                proposal=value.proposal,
                npc_performance=value.npc_performance.model_dump(mode="json")
                if value.npc_performance is not None
                else None,
                counterpart=value.counterpart,
                can_answer=not ended
                and value.phase == "invited"
                and viewer.user_id == value.counterpart
                and broken.current(state, value.actor)
                and broken.current(state, value.target),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        from girlframe.services.m3_learned_bonded_alpha import parent_lesson
        from girlframe.services.m3_learned_sex import cancelled

        return [
            dict(
                id=x.id,
                revision=state.revision,
                kind="alpha_sex_consent",
                label="Confirm your original voluntary Alpha source",
                actionable=True,
            )
            for x in rules.sessions(state)
            if not cancelled(self.game, c, state, x.learned_source or parent_lesson(state, x))
            and x.phase == "invited"
            and x.counterpart == viewer.user_id
            and broken.current(state, x.actor)
            and broken.current(state, x.target)
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
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe only your actual voluntary source interaction")

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
                    "STALE_SOURCE: finish pending Plays and reopen actual source controls"
                )
            event, identity = str(uuid4()), str(uuid4())
            cast = _cast(self.game, c, state, channel)
            assert self.store.policy.m3_approval is not None
            value = rules.Session(
                id=identity,
                actor=actor,
                bonded_source=bonded_source,
                changeling_source=changeling_source,
                target=target,
                caster=viewer.user_id,
                counterpart=resolve(state, target, profiles(c, self.store.campaign_id)).controller,
                actor_vessel=resolve(state, actor, profiles(c, self.store.campaign_id)).vessel_id
                if target.kind == "npc"
                else None,
                target_vessel=resolve(state, target, profiles(c, self.store.campaign_id)).vessel_id
                if target.kind == "npc"
                else None,
                cast=cast,
                registry=self.store.policy.m3_approval.registry_sha256,
                proposed_event=event,
                proposal=account,
            )
            if learned_source is not None:
                from girlframe.services.m3_learned_sex import reserve_invitation

                link = reserve_invitation(self.game, c, state, value, rules.RULE, learned_source)
                value = value.model_copy(update=dict(learned_source=link))
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

                bind_delegation(self.game, c, state, bonded_source, value.id, rules.RULE, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.alpha_sex_invited",
                state,
                event_id=event,
                session=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.alpha_sex_invited",
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
        """Owner-only unused source release; never a fictional refusal."""

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)

            if (
                state.revision != expected
                or viewer.user_id != value.caster
                or not broken.current(state, value.actor)
                or (value.learned_source is None and value.bonded_source is None)
                or (
                    value.bonded_source is not None
                    and bonded.get(state, value.bonded_source).changeling_source is not None
                )
                or value.changeling_source is not None
                or value.phase not in ("invited", "accepted")
                or value.action is not None
                or value.effect_event is not None
                or value.sleep_event is not None
                or value.wake_event is not None
            ):
                raise WorkflowError(
                    "Only the original owner may withdraw this unused original invitation"
                )
            actions = t.m2["m2_actions"]
            if c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    sa.or_(
                        sa.func.json_extract(actions.c.body_json, "$.alpha_sex.session")
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
            if value.learned_source is not None:
                withdraw_invitation(self.game, c, state, value, event)
            rules.put(state, value.model_copy(update={"phase": "withdrawn"}))
            if value.bonded_source is not None:
                from girlframe.services.m3_learned_bonded_alpha import release

                release(self.game, c, state, identity, viewer.user_id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.alpha_sex_withdrawn",
                state,
                event_id=event,
                session=identity,
            )
            return dict(id=identity, phase="withdrawn")

        return self.store._write(
            viewer,
            key,
            "m3.alpha_sex_withdrawn",
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
            raise WorkflowError(
                "The actual counterpart answers for their own voluntary interaction"
            )

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if (
                state.revision != expected
                or value.phase != "invited"
                or viewer.user_id != value.counterpart
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Only the original counterpart owns this current source answer")
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
            contact = None
            if value.target.kind == "npc" and accept:
                from girlframe.services.m3_oldgen_sex import _counterpart

                if (
                    not npc_contact_account
                    or not npc_contact_account.strip()
                    or len(npc_contact_account) > 1200
                ):
                    raise WorkflowError(
                        "Attest actual physical contact outside enclosures for this invitation"
                    )
                other = _counterpart(self.game, c, state, value.target)
                own = resolve(state, value.actor, profiles(c, self.store.campaign_id))
                if (
                    other.controller != value.counterpart
                    or other.vessel_id != value.target_vessel
                    or own.vessel_id != value.actor_vessel
                    or own.vessel_id is None
                    or own.cell is None
                    or own.cell != other.cell
                ):
                    raise WorkflowError("Preserve original NPC controller, bodies and contact cell")
                contact = rules.NpcContact(
                    session=value.id,
                    actor=value.actor,
                    target=value.target,
                    controller=value.counterpart,
                    vessel=other.vessel_id,
                    actor_vessel=own.vessel_id,
                    cell=own.cell,
                    cast=value.cast,
                    revision=state.revision,
                    event=event,
                    account=npc_contact_account,
                )
            elif npc_contact_account is not None:
                raise WorkflowError(
                    "Contact evidence belongs only to an accepted actual NPC source"
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
                from girlframe.services.m3_learned_bonded_alpha import release

                if bonded.get(state, value.bonded_source).changeling_source is None:
                    release(self.game, c, state, identity, viewer.user_id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.alpha_sex_consent",
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
            "m3.alpha_sex_consent",
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

    def track(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if viewer.user_id != value.caster or not rules.tracking(state, value):
                raise WorkflowError(
                    "Scent tracking lasts only while this original is Broken from this Play"
                )
            target = resolve(state, value.target, profiles(c, self.store.campaign_id))
            if target.cell is None or target.offstage_source:
                raise WorkflowError(
                    "TRACK_POSITION_REQUIRED: establish the actual body location first"
                )
            return dict(
                target=value.target.model_dump(mode="json"),
                label=target.label,
                cell=target.cell,
                moved=False,
            )
