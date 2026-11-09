"""Human-owned Easy Target choices backed by actual performances and effects."""

import json
from typing import Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, shift_status
from girlframe.engine.m3_actor_bonds import change, current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "easy_target_select",
    "easy_target_tag",
    "easy_target_react",
    "easy_target_validate",
    "easy_target_child",
    "easy_target_bond",
    "easy_target_judge",
    "easy_target_failure",
    "easy_target_contempt",
)


def handles(kind: str) -> bool:
    return kind.startswith("easy_target_")


def _copy(state: GameState, changed: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(changed, key))


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _get[T: Model](state: GameState, model: type[T], identity: str) -> T:
    try:
        return rules.get(state, model, identity)
    except ValueError as error:
        raise WorkflowError(str(error)) from None


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    _access(game, c, viewer)
    actor = current_ref(state, viewer.user_id)
    actual = _native(game, c, state, actor)
    sheet = state.sheets[actor.entity]
    scene = _cast(game, c, state, channel)
    handler = active_handler(state)
    others = [x for x in scene.roles if x.actor != actor]
    from girlframe.services.m3_learned_plays import available

    owns = sheet.girl == "NEWGIRL" and has_rule(sheet, rules.RULE, "NEWGIRL")
    from girlframe.services.m3_required_plays import direct_nomination

    nominated = direct_nomination(game, c, state, actor, prepared, channel)
    if (
        not (owns or available(game, c, state, actor, rules.RULE, action_id) is not None)
        or not others
        or handler is None
        or prepared.parent
        or (prepared.source_work and not nominated)
        or prepared.off_duty_id
        or prepared.target is not None
        or prepared.target_actor is not None
        or not any(x.actor == actor and x.controller == viewer.user_id for x in scene.roles)
    ):
        raise WorkflowError(
            "Use the actual native Newgirl's mistake with other actual people in this scene"
        )
    for role in scene.roles:
        person = resolve(
            state, role.actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if (
            person.controller != role.controller
            or not person.alive
            or person.offstage_source is not None
            or (person.cell is not None and actual.cell is not None and person.cell != actual.cell)
        ):
            raise WorkflowError(
                "Bind actual living present people and their original human controllers"
            )
    if scene not in state.scene_casts:
        state.scene_casts.append(scene)
    assert game.store.policy.m3_approval is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        caster=viewer.user_id,
        handler=handler.model_dump(mode="json"),
        handler_controller=state.handler,
        cast=scene.model_dump(mode="json"),
        cast_sha256=fingerprint(scene),
        table=sorted({x.controller for x in scene.roles} | {state.handler}),
        registry=game.store.policy.m3_approval.registry_sha256,
        phase="unrolled",
    )


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    expected = prepare(
        game,
        c,
        viewer,
        state,
        PlayInput.model_validate(action["data"]["prepared"]),
        int(action["channel_id"]),
        action_id=action["id"],
    )
    if action["data"]["easy_target"] != expected:
        raise WorkflowError(
            "Reopen the unchanged original Easy Target cast before spending or rolling"
        )


def _session(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> rules.Session:
    value = _get(state, rules.Session, action["id"])
    meta = action["data"]["easy_target"]
    event, total = _roll_source(game, c, action)
    if (
        value.roll_event != event
        or value.total != total
        or value.actor.model_dump(mode="json") != meta["actor"]
        or value.cast.model_dump(mode="json") != meta["cast"]
        or value.handler.model_dump(mode="json") != meta["handler"]
        or value.caster != meta["caster"]
        or value.handler_controller != meta["handler_controller"]
        or fingerprint(value.cast) != meta["cast_sha256"]
    ):
        raise WorkflowError("Recover the actual source roll and original scene people")
    from girlframe.services.m3_learned_plays import prove_consumed

    if not prove_consumed(game, c, state, action, rules.RULE, event):
        born = _history(c, game, event)
        sheet = born.sheets.get(value.actor.entity)
        if (
            sheet is None
            or sheet.character_id != value.actor.incarnation
            or sheet.girl != "NEWGIRL"
            or not has_rule(sheet, rules.RULE, "NEWGIRL")
        ):
            raise WorkflowError("Prove the original native or genuinely learned Easy Target source")
    return value


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Reaction:
    value = _get(state, rules.Reaction, identity)
    parent = game.action(c, value.session)
    source = _session(game, c, state, parent)
    birth = _history(c, game, value.event)
    born = _get(birth, rules.Reaction, identity)
    original = _get(birth, rules.Session, source.id)
    if any(
        getattr(source, key) != getattr(original, key)
        for key in (
            "actor",
            "caster",
            "handler",
            "handler_controller",
            "cast",
            "total",
            "roll_event",
            "selected",
            "tag",
            "tag_event",
        )
    ):
        raise WorkflowError("Preserve the actual original cast, selection, Tag and source roll")
    stable = (
        "id",
        "session",
        "actor",
        "controller",
        "choice",
        "event",
        "urge",
        "account",
        "primary",
        "performer",
        "play",
        "context",
    )
    if (
        any(getattr(value, key) != getattr(born, key) for key in stable)
        or not any(
            x.actor == value.actor and x.controller == value.controller for x in source.cast.roles
        )
        or value.actor == source.actor
    ):
        raise WorkflowError("Preserve this original person's actual owned urge")
    answer = _response(
        game,
        c,
        source.id,
        value.choice,
        value.event,
        value.controller,
        "easy_target_react:" + value.actor.token,
    )
    if answer.options != (value.urge,) or answer.text.strip() != value.account:
        raise WorkflowError("Recover the actual role's immutable choice response")
    return value


def _request(
    game: GameService,
    c: Connection,
    action: dict[str, Any],
    owner: int,
    kind: str,
    value: rules.Reaction,
) -> str:
    return game.request(
        c,
        action,
        owner,
        kind + ":" + value.actor.token,
        dict(work=value.id, actor=value.actor.model_dump(mode="json")),
    )


def _reactions(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    source: rules.Session,
) -> None:
    roles = [
        x
        for x in source.cast.roles
        if x.actor != source.actor
        and (source.total <= 7 or source.total >= 11 or x.actor == source.selected)
    ]
    for role in roles:
        game.request(
            c,
            action,
            role.controller,
            "easy_target_react:" + role.actor.token,
            dict(actor=role.actor.model_dump(mode="json")),
        )
    action["data"]["easy_target"]["phase"] = "reacting"


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["easy_target"]
    if meta["phase"] != "unrolled":
        raise WorkflowError("Resume actual Easy Target without repeating its roll")
    event, total = _roll_source(game, c, action)
    source = rules.Session(
        id=action["id"],
        actor=ActorRef.model_validate(meta["actor"]),
        caster=meta["caster"],
        handler=ActorRef.model_validate(meta["handler"]),
        handler_controller=meta["handler_controller"],
        cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
        total=total,
        roll_event=event,
        event=action["data"].get("response_event") or event,
    )
    rules.put(state, source)
    if total <= 7:
        shift_status(state, source.caster, -1)
        _reactions(game, c, state, action, source)
    else:
        meta["phase"] = "selecting"
        game.request(c, action, source.caster, "easy_target_select")


def _finish(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if game.pending(c, action["id"]):
        return
    if any(
        x.session == action["id"] and not x.completed_event
        for x in rules.records(state, rules.Reaction)
    ):
        game.save_action(c, action, state="awaiting_choices")
        return
    from girlframe.services.m2_choices import ChoiceEngine

    action["data"]["easy_target"]["phase"] = "complete"
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def _activate(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    source = _session(game, c, state, action)
    if not rules.settled(state, source):
        return
    # A cohort cannot turn another person's optional pass into a forced urge.
    invalid = []
    for value in rules.records(state, rules.Reaction):
        if value.session != source.id or value.urge != "cohort":
            continue
        primary = _get(state, rules.Reaction, value.primary or "")
        if (
            primary.session != value.session
            or primary.actor == value.actor
            or primary.urge in ("pass", "cohort")
        ):
            invalid.append(value)
    if invalid:
        for value in invalid:
            rules.put(state, value.model_copy(update=dict(rechoosing=True)))
            game.request(
                c,
                action,
                value.controller,
                "easy_target_react:" + value.actor.token,
                dict(
                    actor=value.actor.model_dump(mode="json"),
                    reason="The selected person chose no primary action; "
                    "choose your own valid reaction",
                ),
            )
        return
    action["data"]["easy_target"]["phase"] = "performing"
    for value in rules.records(state, rules.Reaction):
        if value.session != source.id or value.completed_event or value.validation_event:
            continue
        if value.urge == "pass":
            rules.put(state, value.model_copy(update=dict(completed_event=value.event)))
        elif value.urge == "contempt":
            _request(game, c, action, value.controller, "easy_target_contempt", value)
        elif value.urge == "cohort":
            primary = _get(state, rules.Reaction, value.primary or "")
            if (
                primary.session != value.session
                or primary.actor == value.actor
                or primary.urge in ("pass", "cohort")
            ):
                raise WorkflowError("Go along with an actual other selected primary action")
            _request(game, c, action, value.controller, "easy_target_child", value)
            rules.put(state, value.model_copy(update=dict(validation_event=value.event)))
        else:
            _request(game, c, action, source.handler_controller, "easy_target_validate", value)
    _finish(game, c, state, action)


def _consequence(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    value: rules.Reaction,
    event: str,
) -> None:
    source = _session(game, c, state, action)
    if value.exemption:
        rules.put(
            state, value.model_copy(update=dict(completed_event=event, consequence="cohort-exempt"))
        )
    elif value.urge == "hurt":
        from girlframe.services.m3_role_punishments import open_case

        identity = "easy-target-punishment:" + value.id
        changed, _ = open_case(
            state,
            profiles(c, game.store.campaign_id),
            actor=source.handler,
            target=value.actor,
            chooser=source.actor,
            source_kind="easy_target",
            action=source.id,
            source_event=event,
            identity=identity,
            source_work=value.id,
        )
        _copy(state, changed)
        rules.put(state, value.model_copy(update=dict(consequence=identity)))
    elif value.urge == "use":
        _request(game, c, action, source.caster, "easy_target_bond", value)
    elif value.urge == "request":
        _request(game, c, action, value.controller, "easy_target_judge", value)
    elif value.urge == "protect":
        rules.put(
            state, value.model_copy(update=dict(protection_event=event, completed_event=event))
        )
    else:
        rules.put(state, value.model_copy(update=dict(completed_event=event)))


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    source = _session(game, c, state, action)
    kind = row["kind"].split(":")[0]
    body = json.loads(row["body_json"])
    event = action["data"]["response_event"]
    if (
        not answer.text.strip()
        or len(answer.text) > 1200
        or answer.denied
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Give your actual source-specific account and exact printed choice")
    if kind == "easy_target_select":
        if len(answer.options) != 1 or source.selected or answer.fields or answer.flag is not None:
            raise WorkflowError("Select one other actual scene person")
        role = next(
            (
                x
                for x in source.cast.roles
                if x.actor != source.actor and x.actor.token == answer.options[0]
            ),
            None,
        )
        if role is None:
            raise WorkflowError("Select an actual original other scene person")
        rules.put(state, source.model_copy(update=dict(selected=role.actor)))
        game.request(
            c,
            action,
            role.controller,
            "easy_target_tag",
            dict(actor=role.actor.model_dump(mode="json")),
        )
    elif kind == "easy_target_tag":
        giver = ActorRef.model_validate(body["actor"])
        if (
            source.selected != giver
            or source.tag
            or answer.options
            or answer.fields
            or answer.flag is not None
            or len(answer.text) > 100
        ):
            raise WorkflowError("The actual selected person authors their real Tag")
        changed = give_tag(
            state,
            profiles(c, game.store.campaign_id),
            source.actor,
            giver,
            answer.text.strip(),
            event,
            event,
            tuple(x.controller for x in source.cast.roles),
        )
        _copy(state, changed)
        source = source.model_copy(update=dict(tag=event, tag_event=event))
        rules.put(state, source)
        _reactions(game, c, state, action, source)
    elif kind == "easy_target_react":
        actor = ActorRef.model_validate(body["actor"])
        role = next(x for x in source.cast.roles if x.actor == actor)
        allowed = rules.choices(source) + (("pass",) if source.total >= 11 else ())
        if (
            len(answer.options) != 1
            or answer.options[0] not in allowed
            or answer.flag is not None
            or set(answer.fields) - {"primary", "performer", "play", "context"}
        ):
            raise WorkflowError("Choose your own printed urge; only high reactions are optional")
        urge = cast(rules.Urge, answer.options[0])
        performer: ActorRef | None = source.actor if urge in ("request", "use") else actor
        if answer.fields.get("performer"):
            performer = next(
                (x for x in (source.actor, actor) if x.token == answer.fields["performer"]), None
            )
            if performer is None:
                raise WorkflowError("Use the actual reactor or Newgirl as the owned performer")
        primary = answer.fields.get("primary")
        if urge == "cohort" and (not primary or primary == rules.identity(source.id, actor)):
            raise WorkflowError("Choose the actual other person's primary reaction")
        if urge not in ("pass", "contempt", "cohort") and (
            (
                not answer.fields.get("play")
                and not (urge == "hurt" and actor.kind == "npc" and performer == actor)
            )
            or not answer.fields.get("context", "").strip()
        ):
            raise WorkflowError("Bind an appropriate real implemented Play and its actual trigger")
        value = rules.Reaction(
            id=rules.identity(source.id, actor),
            session=source.id,
            actor=actor,
            controller=role.controller,
            choice=row["id"],
            event=event,
            urge=urge,
            account=answer.text.strip(),
            primary=primary,
            performer=performer,
            play=answer.fields.get("play"),
            context=answer.fields.get("context", ""),
        )
        rules.put(state, value)
        _activate(game, c, state, action)
    else:
        value = _get(state, rules.Reaction, body["work"])
        if value.session != source.id:
            raise WorkflowError("Keep this exact original person's source work")
        if kind == "easy_target_validate":
            if answer.flag is not True or answer.options or answer.fields:
                raise WorkflowError(
                    "The original Handler must validate the real supported performance "
                    "and its actual trigger"
                )
            value = value.model_copy(update=dict(validation_event=event))
            rules.put(state, value)
            if value.performer is None:
                raise WorkflowError("Use the original actual performer")
            owner = resolve(
                state,
                value.performer,
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            ).controller
            _request(game, c, action, owner, "easy_target_child", value)
        elif kind == "easy_target_child":
            if _npc_hurt_reaction(value):
                if answer.options or answer.fields or answer.flag is not None:
                    raise WorkflowError("Record only this actual NPC's performed bodily action")
                _npc_hurt_context(game, c, state, value)
                if any(
                    x.reaction == value.id and not x.completed_event
                    for x in rules.records(state, rules.NpcHurt)
                ):
                    raise WorkflowError("Finish the actual outstanding NPC injury first")
                hurt = rules.NpcHurt(
                    id=str(uuid4()),
                    reaction=value.id,
                    session=value.session,
                    actor=value.actor,
                    controller=value.controller,
                    target=source.actor,
                    handler=source.handler,
                    cast=_cast(game, c, state, source.cast.channel),
                    choice=row["id"],
                    account=answer.text.strip(),
                    event=event,
                )
                rules.put(state, hurt)
                game.request(
                    c,
                    action,
                    source.caster,
                    "battle_target_damage",
                    dict(easy_target_npc_hurt=hurt.id, work=value.id),
                )
            else:
                raise WorkflowError(
                    "REQUIRED_ACTUAL_PERFORMANCE: finish the genuine child Play "
                    "and its actual consequences"
                )
        elif kind == "easy_target_bond":
            if (
                answer.flag is None
                or answer.options
                or answer.fields
                or not value.performance_event
            ):
                raise WorkflowError(
                    "The original Newgirl chooses whether to deepen their actual Bond after use"
                )
            if answer.flag:
                _copy(state, change(state, source.actor, value.actor, 1, event))
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        consequence="bond" if answer.flag else "bond-declined",
                        completed_event=event,
                    )
                ),
            )
        elif kind == "easy_target_judge":
            if (
                answer.flag is None
                or answer.options
                or answer.fields
                or not value.performance_event
            ):
                raise WorkflowError(
                    "The original requester judges the Newgirl's actual completed performance"
                )
            if answer.flag:
                shift_status(state, source.caster, 1)
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        consequence="well" if answer.flag else "poor", completed_event=event
                    )
                ),
            )
        elif kind == "easy_target_failure":
            if answer.flag is None or answer.options or answer.fields or not value.failure:
                raise WorkflowError(
                    "The original Newgirl chooses a real Tag after actual protection failure"
                )
            if answer.flag:
                if len(answer.text) > 100:
                    raise WorkflowError("Use a real Tag label of at most 100 characters")
                changed = give_tag(
                    state,
                    profiles(c, game.store.campaign_id),
                    value.actor,
                    source.actor,
                    answer.text.strip(),
                    event,
                    event,
                    (source.caster, value.controller),
                )
                _copy(state, changed)
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        consequence="failure-tag" if answer.flag else "failure-declined",
                        completed_event=event,
                    )
                ),
            )
        elif kind == "easy_target_contempt":
            if (
                answer.options not in (("look",), ("spit",), ("leave",))
                or answer.fields
                or answer.flag is not None
                or not rules.settled(state, source)
            ):
                raise WorkflowError(
                    "Perform your actual disgusted look, spit, or exact actor departure"
                )
            if answer.options == ("leave",):
                from girlframe.services.m3_cast import withdraw_easy_target

                withdraw_easy_target(game, c, state, value.id, event)
                value = value.model_copy(update=dict(departure_event=event))
            if not value.exemption:
                shift_status(state, source.caster, -1)
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        performance_event=event,
                        consequence="cohort-exempt" if value.exemption else "status-lowered",
                        completed_event=event,
                    )
                ),
            )
        else:
            raise WorkflowError("Recover the exact Easy Target source choice")
    _finish(game, c, state, action)


apply_choice = apply


def _npc_hurt_reaction(value: rules.Reaction) -> bool:
    return (
        value.urge == "hurt"
        and value.actor.kind == "npc"
        and value.performer == value.actor
        and value.play is None
    )


def _npc_hurt_context(
    game: GameService, c: Connection, state: GameState, value: rules.Reaction
) -> rules.Session:
    """Current physical performance authority; never a grant of a PC Play."""
    prove(game, c, state, value.id)
    parent = game.action(c, value.session)
    source = _session(game, c, state, parent)
    if (
        not _npc_hurt_reaction(value)
        or not rules.settled(state, source)
        or not value.validation_event
        or value.child
        or value.performance_event
        or value.completed_event
        or parent["state"] in ("complete", "aborted")
        or current_ref(state, source.caster) != source.actor
        or active_handler(state) != source.handler
        or state.handler != source.handler_controller
    ):
        raise WorkflowError("Use this actual unperformed original NPC hurt source")
    validation_row = next(
        (
            x
            for x in c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.action_id == source.id,
                    t.m2["m2_choices"].c.kind == "easy_target_validate:" + value.actor.token,
                )
            ).mappings()
            if json.loads(x["body_json"]).get("work") == value.id
        ),
        None,
    )
    if validation_row is None:
        raise WorkflowError("Recover the original Handler's actual injury validation")
    validation = _response(
        game,
        c,
        source.id,
        validation_row["id"],
        value.validation_event,
        source.handler_controller,
        "easy_target_validate:" + value.actor.token,
    )
    if validation.flag is not True or not validation.text.strip():
        raise WorkflowError("Preserve the original Handler's actual supported-injury account")
    bound = profiles(c, game.store.campaign_id)
    actor = resolve(state, value.actor, bound, require_current_profile=False)
    target = _native(game, c, state, source.actor)
    npc = (
        next((x for x in state.world.npcs if x.id == value.actor.entity), None)
        if state.world
        else None
    )
    if (
        npc is None
        or npc.source_kind == "wyvern_wraith"
        or actor.rules != "npc"
        or not actor.alive
        or actor.controller != value.controller
        or actor.offstage_source is not None
        or actor.custody not in (None, "free")
        or target.inside_frame is not False
        or actor.cell is None
        or actor.cell != target.cell
    ):
        raise WorkflowError("Use the actual free present NPC and the original exposed Girl body")
    scene = _cast(game, c, state, source.cast.channel)
    departed = {
        x.actor
        for x in rules.records(state, rules.Reaction)
        if x.session == source.id and x.departure_event
    }
    if (
        scene.id != source.cast.id
        or not scene.open
        or scene.facilitator != source.cast.facilitator
        or scene.roles != tuple(x for x in source.cast.roles if x.actor not in departed)
    ):
        raise WorkflowError("Preserve the actual original bodily-performance scene and controllers")
    if any(
        x.session == source.id and x.urge == "cohort" and x.primary == value.id
        for x in rules.records(state, rules.Reaction)
    ):
        raise WorkflowError(
            "REQUIRED_NPC_HURT_COHORT_ADAPTER: actual non-roll assistance is not a Tag roll"
        )
    return source


def prove_npc_hurt(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.NpcHurt:
    hurt = _get(state, rules.NpcHurt, identity)
    born = _history(c, game, hurt.event)
    original = _get(born, rules.NpcHurt, identity)
    value = prove(game, c, born, hurt.reaction)
    source = _session(game, c, born, game.action(c, hurt.session))
    immutable = (
        "id",
        "reaction",
        "session",
        "actor",
        "controller",
        "target",
        "handler",
        "cast",
        "choice",
        "account",
        "event",
    )
    if (
        any(getattr(hurt, key) != getattr(original, key) for key in immutable)
        or not _npc_hurt_reaction(value)
        or value.session != hurt.session
        or value.actor != hurt.actor
        or value.controller != hurt.controller
        or hurt.target != source.actor
        or hurt.handler != source.handler
        or not value.validation_event
    ):
        raise WorkflowError("Recover the exact original actual NPC hurt performance")
    answer = _response(
        game,
        c,
        source.id,
        hurt.choice,
        hurt.event,
        hurt.controller,
        "easy_target_child:" + value.actor.token,
    )
    if (
        answer.text.strip() != hurt.account
        or answer.options
        or answer.fields
        or answer.flag is not None
    ):
        raise WorkflowError("Preserve the actual NPC controller's original performance account")
    # Historical body proof grants no current account or scene authority.
    from girlframe.services.m3_actor_history import snapshot_profiles

    bound = snapshot_profiles(c, game.store.campaign_id, born)
    actor = resolve(born, hurt.actor, bound, require_current_profile=False)
    target = resolve(born, hurt.target, bound, require_current_profile=False)
    if (
        actor.rules != "npc"
        or not actor.alive
        or actor.controller != hurt.controller
        or actor.offstage_source is not None
        or actor.custody not in (None, "free")
        or not target.alive
        or target.inside_frame is not False
        or actor.cell is None
        or actor.cell != target.cell
        or hurt.cast not in born.scene_casts
        or hurt.cast.id != source.cast.id
        or not any(
            x.actor == hurt.actor and x.controller == hurt.controller for x in hurt.cast.roles
        )
    ):
        raise WorkflowError("Prove the original real bodies, controller and source scene at birth")
    if hurt.damage_event:
        damaged = _get(_history(c, game, hurt.damage_event), rules.NpcHurt, hurt.id)
        if (
            hurt.asset != damaged.asset
            or hurt.asset_choice != damaged.asset_choice
            or hurt.damage_event != damaged.damage_event
            or hurt.work != damaged.work
        ):
            raise WorkflowError("Preserve this actual injury and every original damage obligation")
    elif hurt.asset or hurt.asset_choice or hurt.work:
        raise WorkflowError("A real selected injury needs its canonical damage event")
    return hurt


def _npc_damage_row(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> rules.NpcHurt:
    identity = json.loads(row["body_json"]).get("easy_target_npc_hurt")
    hurt = prove_npc_hurt(game, c, state, identity or "")
    source = _get(state, rules.Session, hurt.session)
    if (
        row["kind"] != "battle_target_damage"
        or row["action_id"] != hurt.session
        or action["id"] != hurt.session
        or row["actor_id"] != str(source.caster)
        or json.loads(row["body_json"]).get("work") != hurt.reaction
        or hurt.damage_event
        or hurt.completed_event
    ):
        raise WorkflowError("The actual original Newgirl owns this exact bodily injury selection")
    _npc_hurt_context(game, c, state, _get(state, rules.Reaction, hurt.reaction))
    return hurt


def npc_hurt_damage_projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    hurt = _npc_damage_row(game, c, state, action, row)
    actual = _native(game, c, state, hurt.target)
    return dict(
        kind="battle_target_damage",
        target=hurt.target.model_dump(mode="json"),
        assets=[
            dict(id=x.id, name=x.name)
            for x in actual.assets
            if x.family == "girl" and not x.damaged
        ],
    )


def apply_npc_hurt_damage(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    hurt = _npc_damage_row(game, c, state, action, row)
    legal = npc_hurt_damage_projection(game, c, state, action, row)
    if (
        set(answer.fields) != {"asset"}
        or answer.fields["asset"] not in {x["id"] for x in legal["assets"]}
        or answer.options
        or answer.text
        or answer.flag is not None
        or answer.denied
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Select one actual legal undamaged Girl Asset through its owned choice")
    event = action["data"]["response_event"]
    hurt = hurt.model_copy(
        update=dict(
            asset=answer.fields["asset"],
            asset_choice=row["id"],
            damage_event=event,
        )
    )
    rules.put(state, hurt)
    # Publish only the actual pending response state within this transaction;
    # canonical response/history are still required for later readback.
    game.save_action(c, action)
    from girlframe.services.m3_battle import damage_actor

    changed, work = damage_actor(
        game,
        c,
        state,
        target=hurt.target,
        asset_id=hurt.asset,
        source_action=hurt.session,
        source_work=hurt.id,
        event=event,
        actor=hurt.actor,
        opponent=hurt.actor,
        chooser_controller=hurt.controller,
        occurrence="easy_target_npc_hurt:" + hurt.id,
        physical_blow=True,
    )
    _copy(state, changed)
    rules.put(state, hurt.model_copy(update=dict(work=work)))
    _finish(game, c, state, action)


def prove_npc_hurt_damage(
    game: GameService,
    c: Connection,
    state: GameState,
    hurt_id: str,
    target: ActorRef,
    asset: str | None,
    event: str,
    actor: ActorRef | None,
    chooser_controller: int | None,
) -> rules.NpcHurt:
    hurt = _get(state, rules.NpcHurt, hurt_id)
    selected_asset = hurt.asset
    if selected_asset is None or hurt.asset_choice is None or hurt.damage_event is None:
        raise WorkflowError("Prove the actual target-owned Girl Asset injury first")
    staged = (
        hurt.damage_event == event
        and c.scalar(
            sa.select(t.events.c.id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
            )
        )
        is None
    )
    # Birth must already be canonical even when the actual injury is being staged.
    birth = _get(_history(c, game, hurt.event), rules.NpcHurt, hurt.id)
    if staged:
        prove_npc_hurt(game, c, _history(c, game, hurt.event), hurt.id)
        if any(
            getattr(hurt, key) != getattr(birth, key)
            for key in (
                "id",
                "reaction",
                "session",
                "actor",
                "controller",
                "target",
                "handler",
                "cast",
                "choice",
                "account",
                "event",
            )
        ):
            raise WorkflowError("Preserve the canonical NPC performance before actual injury")
        value = _get(state, rules.Reaction, hurt.reaction)
        source = _npc_hurt_context(game, c, state, value)
        row = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.id == hurt.asset_choice,
                )
            )
            .mappings()
            .first()
        )
        action = game.action(c, hurt.session)
        selected = (
            action["data"].get("choices", {}).get("battle_target_damage:" + str(source.caster))
        )
        if (
            row is None
            or row["state"] != "answered"
            or row["action_id"] != hurt.session
            or row["actor_id"] != str(source.caster)
            or json.loads(row["body_json"]).get("easy_target_npc_hurt") != hurt.id
            or action["data"].get("response_event") != event
            or selected != ChoiceAnswer(fields={"asset": selected_asset}).model_dump(mode="json")
        ):
            raise WorkflowError(
                "Prove the actual current target-owned injury response before effects"
            )
    else:
        prove_npc_hurt(game, c, state, hurt.id)
        if not hurt.damage_event or not hurt.asset_choice:
            raise WorkflowError("Recover the real original NPC injury selection")
        source = _get(_history(c, game, hurt.damage_event), rules.Session, hurt.session)
        selected_answer = _response(
            game,
            c,
            hurt.session,
            hurt.asset_choice,
            hurt.damage_event,
            source.caster,
            "battle_target_damage",
        )
        if selected_answer != ChoiceAnswer(fields={"asset": selected_asset}):
            raise WorkflowError("Preserve the real Newgirl's exact selected injury")
    if (
        hurt.target != target
        or hurt.asset != asset
        or hurt.actor != actor
        or hurt.controller != chooser_controller
        or hurt.completed_event
    ):
        raise WorkflowError("Only this actual NPC performance grants this exact bodily injury")
    return hurt


def synchronize_npc_hurt(
    game: GameService, c: Connection, action: dict[str, Any], event: str
) -> None:
    if not action["data"].get("easy_target"):
        return
    from girlframe.services.m3_battle import synchronize_damage

    synchronize_damage(game, c, event)
    state = load_state(c, game.store.campaign_id)
    for hurt in rules.records(state, rules.NpcHurt):
        if hurt.session != action["id"] or not hurt.damage_event or hurt.completed_event:
            continue
        _complete_npc_hurt(game, c, hurt, event)


def _complete_npc_hurt(game: GameService, c: Connection, hurt: rules.NpcHurt, event: str) -> bool:
    state = load_state(c, game.store.campaign_id)
    hurt = prove_npc_hurt(game, c, state, hurt.id)
    if hurt.completed_event:
        return True
    work = t.m3["m3_required_work"]
    for identity in hurt.work:
        row = (
            c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == game.store.campaign_id,
                    work.c.id == identity,
                )
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["state"] != "resolved":
            return False
    parent = game.action(c, hurt.session)
    value = prove(game, c, state, hurt.reaction)
    if value.performance_event or value.completed_event:
        raise WorkflowError("Preserve the original single committed NPC hurt consequence")
    harm = next(
        (
            x
            for x in rules.records(state, rules.Harm)
            if (
                x.target == hurt.target
                and x.opponent == hurt.actor
                and x.source_work in (hurt.id, *hurt.work)
                and x.source_action == hurt.session
            )
        ),
        None,
    )
    effect_event = str(uuid4())
    rules.put(state, hurt.model_copy(update=dict(completed_event=effect_event)))
    if harm is None:
        # A real intercepted blow never proves bodily hurt or a Punishment entitlement.
        if not hurt.work:
            raise WorkflowError("Complete actual bodily harm or its real interception first")
        _request(game, c, parent, value.controller, "easy_target_child", value)
    else:
        value = value.model_copy(
            update=dict(
                performance_event=hurt.event,
                consequence_event=effect_event,
                harm=harm.id,
            )
        )
        rules.put(state, value)
        _consequence(game, c, state, parent, value, effect_event)
    _finish(game, c, state, parent)
    game.save_action(c, parent)
    game.event(
        c,
        hurt.controller,
        "easy-target-npc-hurt:" + hurt.id,
        "m3.easy_target_npc_hurt_completed",
        state,
        event_id=effect_event,
        work=hurt.reaction,
        hurt=hurt.id,
        source_event=event,
        harmed=harm is not None,
    )
    if harm is not None:
        from girlframe.services.m3_role_punishments import synchronize as sync_punishment

        sync_punishment(game, c, parent, effect_event)
    return True


def complete_npc_hurt_work(
    game: GameService, c: Connection, row: dict[str, Any], event: str
) -> bool:
    body = json.loads(row["body_json"])
    identity = body.get("source_work")
    state = load_state(c, game.store.campaign_id)
    hurt = next((x for x in rules.records(state, rules.NpcHurt) if x.id == identity), None)
    if hurt is None:
        return False
    if body.get("source_action") != hurt.session or row["id"] not in hurt.work:
        raise WorkflowError("Complete only this original NPC hurt's exact damage work")
    _complete_npc_hurt(game, c, hurt, event)
    return True


def _close(
    game: GameService,
    c: Connection,
    action: dict[str, Any],
    value: rules.Reaction,
    kind: str,
    event: str,
    **fields: Any,
) -> None:
    from girlframe.database import tables as t

    rows = [
        x
        for x in game.pending(c, action["id"])
        if x["kind"] == kind + ":" + value.actor.token
        and json.loads(x["body_json"]).get("work") == value.id
    ]
    if len(rows) != 1:
        raise WorkflowError("Recover the exact real source obligation before completing it")
    row = rows[0]
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
                json.loads(row["body_json"]) | dict(completion_event=event, **fields)
            ),
        )
    )


def prepare_child(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not prepared.source_work or not any(
        x.id == prepared.source_work for x in rules.records(state, rules.Reaction)
    ):
        return None
    _access(game, c, viewer)
    value = prove(game, c, state, prepared.source_work)
    parent = game.action(c, value.session)
    source = _session(game, c, state, parent)
    if (
        not rules.settled(state, source)
        or not value.validation_event
        or value.completed_event
        or value.child
        or value.urge in ("cohort", "contempt", "pass")
    ):
        raise WorkflowError(
            "Settle all real reactions and validate the actual unperformed source first"
        )
    if value.performer is None or value.performer.kind != "pilot":
        raise WorkflowError(
            "UNSUPPORTED_EASY_TARGET_PERFORMER: this actual role needs its genuine Play adapter"
        )
    actual = _native(game, c, state, value.performer)
    pending = next(
        (
            x
            for x in game.pending(c, parent["id"])
            if x["kind"] == "easy_target_child:" + value.actor.token
            and json.loads(x["body_json"]).get("work") == value.id
        ),
        None,
    )
    if (
        viewer.user_id != actual.controller
        or prepared.parent != source.id
        or prepared.play != value.play
        or prepared.context != value.context
        or channel != source.cast.channel
        or prepared.order_id
        or prepared.off_duty_id
        or not prepared.trigger_confirmed
        or pending is None
    ):
        raise WorkflowError("The original actual performer owns this exact genuine triggered child")
    scene = _cast(game, c, state, channel)
    departed = {
        x.actor
        for x in rules.records(state, rules.Reaction)
        if x.session == source.id and x.departure_event
    }
    if (
        scene.roles != tuple(x for x in source.cast.roles if x.actor not in departed)
        or scene.id != source.cast.id
        or not scene.open
        or scene.facilitator != source.cast.facilitator
    ):
        raise WorkflowError(
            "Keep the actual original source cast until this performance is committed"
        )
    if value.urge == "hurt" and (
        prepared.play != "all_out_assault" or prepared.target_actor != source.actor
    ):
        raise WorkflowError(
            "UNSUPPORTED_EASY_TARGET_HARM: bind genuine physical Assault against this Newgirl"
        )
    if value.urge == "protect" and prepared.play != "engage":
        raise WorkflowError(
            "UNSUPPORTED_EASY_TARGET_PROTECTION: bind the actual Engage protect maneuver"
        )
    return dict(
        work=value.id,
        parent=source.id,
        actor=value.performer.model_dump(mode="json"),
        controller=actual.controller,
        choice=pending["id"],
        cast=scene.model_dump(mode="json"),
        table=sorted(
            {x.controller for x in scene.roles}
            | ({scene.facilitator} if scene.facilitator else set())
        ),
    )


def bind_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    scope = action["data"]["easy_target_child"]
    value = prove(game, c, state, scope["work"])
    if (
        value.child
        or value.completed_event
        or action.get("parent_id") != value.session
        or value.performer is None
        or action["actor_id"] != value.performer.entity
        or scope["actor"] != value.performer.model_dump(mode="json")
        or action["data"]["play"] != value.play
    ):
        raise WorkflowError("Bind only the original real performer and exact single source child")
    rules.put(state, value.model_copy(update=dict(child=action["id"], bound_event=event)))


def battle_declaration(
    game: GameService,
    c: Connection,
    source_action: dict[str, Any],
    declaration: Any,
    viewer: GuildViewer,
) -> dict[str, Any] | None:
    if not source_action["data"].get("easy_target"):
        return None
    state = load_state(c, game.store.campaign_id)
    source = _session(game, c, state, source_action)
    values = [
        x
        for x in rules.records(state, rules.Reaction)
        if x.session == source.id
        and x.urge == "hurt"
        and x.actor == declaration.actor
        and x.performer == declaration.actor
        and x.play == declaration.play
        and x.context == declaration.account
        and x.validation_event
        and not x.child
        and not x.completed_event
    ]
    if (
        len(values) != 1
        or declaration.target != source.actor
        or declaration.play != "all_out_assault"
        or viewer.user_id != values[0].controller
        or not rules.settled(state, source)
    ):
        raise WorkflowError(
            "Declare the actual original reactor's required physical attack on this Newgirl"
        )
    value = prove(game, c, state, values[0].id)
    return next(
        (
            x
            for x in game.pending(c, source.id)
            if x["kind"] == "easy_target_child:" + value.actor.token
            and json.loads(x["body_json"]).get("work") == value.id
        ),
        None,
    )


def _assistance(
    game: GameService,
    c: Connection,
    state: GameState,
    parent: dict[str, Any],
    primary: rules.Reaction,
    child: dict[str, Any],
    event: str,
) -> rules.Reaction:
    marker = child["data"].get("tag_marker_applied", {})
    for cohort in rules.records(state, rules.Reaction):
        if (
            cohort.session != primary.session
            or cohort.urge != "cohort"
            or cohort.primary != primary.id
            or cohort.completed_event
        ):
            continue
        prove(game, c, state, cohort.id)
        if (
            marker.get("actor") != cohort.actor.model_dump(mode="json")
            or marker.get("controller") != cohort.controller
            or marker.get("amount", 0) <= 0
            or not any(
                x.get("tag") == marker.get("tag") and x.get("amount", 0) > 0
                for x in child["data"].get("modifiers", ())
            )
        ):
            raise WorkflowError(
                "REQUIRED_COHORT_ASSISTANCE: actually assist the primary "
                "through an original positive Tag modifier"
            )
        _close(game, c, parent, cohort, "easy_target_child", event, assisted_child=child["id"])
        rules.put(
            state,
            cohort.model_copy(
                update=dict(
                    performance_event=event,
                    exemption=primary.id,
                    consequence="cohort-exempt",
                    completed_event=event,
                )
            ),
        )
        primary = primary.model_copy(update=dict(exemption=cohort.id))
    return primary


def complete_child(
    game: GameService, c: Connection, state: GameState, child: dict[str, Any], event: str
) -> bool:
    scope = child["data"].get("easy_target_child")
    if scope is None:
        return False
    value = prove(game, c, state, scope["work"])
    parent = game.action(c, value.session)
    source = _session(game, c, state, parent)
    if (
        value.child != child["id"]
        or child.get("parent_id") != source.id
        or value.performer is None
        or child["actor_id"] != value.performer.entity
        or child["data"]["play"] != value.play
        or child["state"] != "complete"
        or not child["data"].get("receipt")
        or not child["data"].get("result")
        or game.pending(c, child["id"])
    ):
        raise WorkflowError(
            "Complete the genuine original performer's actual child and all ordinary consequences"
        )
    _roll_source(game, c, child)
    if value.performance_event:
        if value.performance_event != event:
            raise WorkflowError("This actual performance was already completed")
        return True
    if value.urge == "protect":
        from girlframe.engine.m3_engage import Maneuver

        maneuvers = tuple(
            Maneuver.model_validate_json(x["body"])
            for x in state.facts
            if x.get("kind") == "engage_maneuver"
        )
        if not any(
            x.source_action == child["id"] and x.actor == value.actor and x.kind == "protect"
            for x in maneuvers
        ):
            raise WorkflowError(
                "REQUIRED_PROTECTION: perform the actual protective Engage "
                "maneuver for this bound ward"
            )
    harm = next(
        (
            x
            for x in rules.records(state, rules.Harm)
            if x.source_action == child["id"]
            and x.target == source.actor
            and x.opponent == value.actor
        ),
        None,
    )
    value = _assistance(game, c, state, parent, value, child, event)
    if value.urge == "hurt" and harm is None:
        rules.put(
            state,
            value.model_copy(
                update=dict(child=None, bound_event=None, children=value.children + (child["id"],))
            ),
        )
        game.save_action(c, parent, state="awaiting_choices")
        return True
    post = (
        c.scalar(
            sa.select(t.events.c.id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        is not None
    )
    effect_event = str(uuid4()) if post else event
    value = value.model_copy(
        update=dict(
            performance_event=event,
            consequence_event=effect_event,
            harm=harm.id if harm else None,
            children=value.children + (child["id"],),
        )
    )
    rules.put(state, value)
    _close(game, c, parent, value, "easy_target_child", effect_event, completed_child=child["id"])
    _consequence(game, c, state, parent, value, effect_event)
    _finish(game, c, state, parent)
    game.save_action(c, parent)
    if post:
        game.event(
            c,
            int(child["actor_id"]),
            "easy-target-performed:" + child["id"],
            "m3.easy_target_performed",
            state,
            event_id=effect_event,
            child=child["id"],
            work=value.id,
        )
        if value.urge == "hurt" and not value.exemption:
            from girlframe.services.m3_role_punishments import synchronize as sync_punishment

            sync_punishment(game, c, parent, effect_event)
    return True


def observe_harm(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    *,
    target: ActorRef,
    opponent: ActorRef | None,
    event: str,
    source_action: str | None,
    source_work: str | None,
    physical_blow: bool | None,
) -> None:
    if physical_blow is not True or before == after or not (source_action or source_work):
        return
    relevant = [x for x in rules.records(after, rules.Session) if x.actor == target]
    if not relevant:
        return
    bound = profiles(c, game.store.campaign_id)
    old = resolve(before, target, bound, require_current_profile=False)
    new = resolve(after, target, bound, require_current_profile=False)
    old_damage = {x.id for x in old.assets if x.damaged and x.family == "girl"}
    new_damage = {x.id for x in new.assets if x.damaged and x.family == "girl"}
    if not (new_damage - old_damage):
        return
    identity = "easy-target-harm:" + event + ":" + target.token
    existing = next((x for x in rules.records(after, rules.Harm) if x.id == identity), None)
    harm = rules.Harm(
        id=identity,
        target=target,
        opponent=opponent,
        event=event,
        source_action=source_action,
        source_work=source_work,
        before=fingerprint(old),
        after=fingerprint(new),
    )
    if existing is not None:
        if existing != harm:
            raise WorkflowError("Preserve the original committed physical harm source")
        return
    rules.put(after, harm)
    for value in rules.records(after, rules.Reaction):
        source = next((x for x in relevant if x.id == value.session), None)
        if source is None or value.urge != "protect" or not value.protection_event or value.failure:
            continue
        incoming = game.action(c, source_action) if source_action else None
        scene = next((x for x in after.scene_casts if x.id == source.cast.id and x.open), None)
        if (
            incoming is None
            or incoming["scene_id"] != source.cast.id
            or scene is None
            or not all(
                any(r.actor == ref and r.controller == owner for r in scene.roles)
                for ref, owner in ((source.actor, source.caster), (value.actor, value.controller))
            )
        ):
            continue
        value = value.model_copy(update=dict(failure=identity, completed_event=None))
        rules.put(after, value)
        # This optional entitlement survives independently of the completed source.
        # The incoming harm's actual Play retains its own channel lock and decisions.
        if value.exemption:
            rules.put(
                after,
                value.model_copy(update=dict(completed_event=event, consequence="cohort-exempt")),
            )


def leave_actor(
    game: GameService, c: Connection, state: GameState, work: str, event: str
) -> ActorRef:
    value = prove(game, c, state, work)
    source = _session(game, c, state, game.action(c, value.session))
    if (
        value.urge != "contempt"
        or value.performance_event
        or not rules.settled(state, source)
        or not any(
            x.id == source.cast.id
            and any(r.actor == value.actor and r.controller == value.controller for r in x.roles)
            for x in state.scene_casts
        )
    ):
        raise WorkflowError("Only the actual original contempt actor may leave this source scene")
    return value.actor


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    value = prove(game, c, state, case.source_work or "")
    source = _session(game, c, state, game.action(c, value.session))
    if (
        case.source_kind != "easy_target"
        or value.urge != "hurt"
        or not value.harm
        or value.exemption
        or value.consequence != case.id
        or case.subject != value.actor
        or case.chooser != source.actor
        or case.executor != source.handler
        or case.action != source.id
        or case.source_event != value.consequence_event
    ):
        raise WorkflowError("Recover the actual hurt and original Newgirl-owned Punishment")


def complete_role_case(c: Connection, game: GameService, case: Any, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    if not case.effect_event or case.completion_event != event:
        raise WorkflowError("Complete the actual chosen Punishment and every real followup")
    value = _get(state, rules.Reaction, case.source_work)
    rules.put(state, value.model_copy(update=dict(completed_event=event)))
    parent = game.action(c, value.session)
    game.event(
        c,
        case.executor_controller,
        "easy-target-punished:" + case.id,
        "m3.easy_target_punished",
        state,
        event_id=str(uuid4()),
        work=value.id,
        punishment=case.id,
    )
    _finish(game, c, state, parent)


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    source = _session(game, c, state, action)
    body = json.loads(row["body_json"])
    value = _get(state, rules.Reaction, body["work"]) if body.get("work") else None
    roles = [
        dict(
            id=x.actor.token,
            actor=x.actor.model_dump(mode="json"),
            controller=x.controller,
            label=resolve(
                state, x.actor, profiles(c, game.store.campaign_id), require_current_profile=False
            ).label,
        )
        for x in source.cast.roles
        if x.actor != source.actor
    ]
    return dict(
        kind=row["kind"].split(":")[0],
        npc_reactor=bool(body.get("actor", {}).get("kind") == "npc"),
        npc_hurt=bool(value and _npc_hurt_reaction(value)),
        roles=roles,
        urges=rules.choices(source) + (("pass",) if source.total >= 11 else ()),
        work=value.model_dump(mode="json") if value else None,
        primaries=[
            dict(
                id=rules.identity(source.id, x.actor),
                label=next(y["label"] for y in roles if y["id"] == x.actor.token),
            )
            for x in source.cast.roles
            if x.actor != source.actor and (value is None or x.actor != value.actor)
        ],
        performer=[
            dict(id=x.token, label="Original Newgirl" if x == source.actor else "Original reactor")
            for x in ((source.actor, value.actor) if value else (source.actor,))
        ],
        bond=depth(state, source.actor, value.actor) if value else None,
        channel=source.cast.channel,
    )


detail = projection


class EasyTargetService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.records(state, rules.Reaction):
            source = _get(state, rules.Session, value.session)
            if viewer.user_id not in (source.caster, source.handler_controller, value.controller):
                continue
            rows = self.game.pending(c, source.id)
            result.append(
                dict(
                    id=value.id,
                    revision=state.revision,
                    label="Easy Target: " + value.urge,
                    pending=(
                        bool(
                            value.failure
                            and not value.completed_event
                            and viewer.user_id == source.caster
                        )
                        or any(
                            x["actor_id"] == str(viewer.user_id)
                            and json.loads(x["body_json"]).get("work") == value.id
                            for x in rows
                        )
                    ),
                    phase="resolved" if value.completed_event else "pending",
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
            value = _get(state, rules.Reaction, identity)
            source = _get(state, rules.Session, value.session)
            if viewer.user_id not in (source.caster, source.handler_controller, value.controller):
                raise WorkflowError(
                    "This private original urge belongs only to its actual participants"
                )
            prove(self.game, c, state, identity)
            return dict(
                id=identity,
                revision=state.revision,
                work=value.model_dump(mode="json"),
                source=source.model_dump(mode="json"),
                npc_hurt=[
                    prove_npc_hurt(self.game, c, state, x.id).model_dump(mode="json")
                    for x in rules.records(state, rules.NpcHurt)
                    if x.reaction == identity
                ],
                can_failure_tag=bool(
                    value.failure
                    and not value.completed_event
                    and not value.exemption
                    and viewer.user_id == source.caster
                ),
                pending=[
                    dict(x)
                    for x in self.game.pending(c, source.id)
                    if x["actor_id"] == str(viewer.user_id)
                    and json.loads(x["body_json"]).get("work") == identity
                ],
            )

    def failure_tag(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, give: bool, account: str
    ) -> dict[str, Any]:
        if type(give) is not bool or not account.strip() or len(account) > (100 if give else 1200):
            raise WorkflowError("Choose your actual optional failure Tag or an explicit decline")

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_EASY_TARGET: reopen the actual saved protection failure")
            value = prove(self.game, c, state, identity)
            source = _session(self.game, c, state, self.game.action(c, value.session))
            if (
                viewer.user_id != source.caster
                or current_ref(state, viewer.user_id) != source.actor
                or not value.failure
                or value.completed_event
                or value.exemption
            ):
                raise WorkflowError(
                    "Only the original Newgirl owns this actual unspent protection-failure Tag"
                )
            harm = _get(state, rules.Harm, value.failure)
            born = _get(_history(c, self.game, harm.event), rules.Harm, harm.id)
            if born != harm or harm.target != source.actor or not value.protection_event:
                raise WorkflowError(
                    "Recover the original committed bodily harm after actual protection"
                )
            event = str(uuid4())
            if give:
                _copy(
                    state,
                    give_tag(
                        state,
                        profiles(c, self.store.campaign_id),
                        value.actor,
                        source.actor,
                        account.strip(),
                        "easy-target-failure-tag:" + value.id,
                        event,
                        (source.caster, value.controller),
                    ),
                )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        consequence="failure-tag" if give else "failure-declined",
                        completed_event=event,
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.easy_target_failure",
                state,
                event_id=event,
                work=value.id,
                given=give,
            )
            return dict(id=value.id, given=give)

        return self.store._write(
            viewer,
            key,
            "m3.easy_target_failure",
            dict(id=identity, revision=revision, give=give, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            from girlframe.services.m3_learned_plays import available

            lesson = (
                available(self.game, c, state, current_ref(state, viewer.user_id), rules.RULE)
                if sheet and sheet.character_id
                else None
            )
            return dict(
                revision=state.revision,
                channel=channel,
                can_start=bool(
                    sheet
                    and (
                        (sheet.girl == "NEWGIRL" and has_rule(sheet, rules.RULE, "NEWGIRL"))
                        or lesson is not None
                    )
                ),
                tasks=self._tasks(c, viewer),
            )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    if not action["data"].get("easy_target"):
        raise WorkflowError("Recover the actual Easy Target source")


def observe_assistance(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    scope = action["data"].get("easy_target_child")
    if scope is None:
        return
    primary = prove(game, c, state, scope["work"])
    if primary.child != action["id"]:
        raise WorkflowError("Keep the actual primary child before recording cohort assistance")
    parent = game.action(c, primary.session)
    marker = action["data"].get("tag_marker_applied", {})
    for cohort in rules.records(state, rules.Reaction):
        if (
            cohort.session != primary.session
            or cohort.urge != "cohort"
            or cohort.primary != primary.id
            or cohort.completed_event
            or marker.get("actor") != cohort.actor.model_dump(mode="json")
            or marker.get("controller") != cohort.controller
            or marker.get("amount", 0) <= 0
        ):
            continue
        prove(game, c, state, cohort.id)
        if not any(
            x.get("tag") == marker.get("tag") and x.get("amount", 0) > 0
            for x in action["data"].get("modifiers", ())
        ):
            raise WorkflowError(
                "Bind assistance to the actually applied positive original actor Tag modifier"
            )
        _close(game, c, parent, cohort, "easy_target_child", event, assisted_child=action["id"])
        rules.put(
            state,
            cohort.model_copy(
                update=dict(
                    performance_event=event,
                    exemption=primary.id,
                    consequence="cohort-exempt",
                    completed_event=event,
                )
            ),
        )
        primary = primary.model_copy(update=dict(exemption=cohort.id))
        rules.put(state, primary)
    game.save_action(c, parent)


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    if action["data"].get("easy_target_child") and action["state"] == "complete":
        complete_child(game, c, load_state(c, game.store.campaign_id), action, event)
