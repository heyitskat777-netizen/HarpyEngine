"""Brutalize's bounded original-Pilot workflow and genuine low counter completion."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection
from sqlalchemy.engine import RowMapping

from girlframe.database import tables as t
from girlframe.engine import m3_alpha as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_princess_sex import HighDirection
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("alpha_damage", "alpha_low", "alpha_counter_play", "alpha_npc_damage", "alpha_npc_mercy")


def _refs(action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    meta = action["data"]["alpha"]
    return ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(meta["target"])


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    access = Access(game.store)
    access.authorize(c, viewer, "plays", director_response=action is not None)
    assert access.registry is not None
    access.registry.require_available(rules.RULE)
    if action is not None:
        meta = action["data"]["alpha"]
        approval = game.store.policy.m3_approval
        if approval is None or approval.registry_sha256 != meta["registry"]:
            raise WorkflowError("Recover the original Brutalize rules approval")
        state = load_state(c, game.store.campaign_id)
        if (
            action["state"] == "complete"
            and action["data"].get("receipt")
            and action["data"].get("princess_child")
            and meta.get("target", {}).get("kind") == "npc"
        ):
            # Actual NPC death removes that actor from the current cast. Reopen
            # only the proved completed directive and immutable original receipt.
            direction = controlled_source(game, c, state, action)
            if direction is not None and direction.completed_event:
                return
        if action["data"].get("ankou_feedback"):
            from girlframe.services.m3_ankou_alpha import completed_npc_death

            if completed_npc_death(game, c, state, action):
                return
        if fingerprint(_cast(game, c, state, int(action["channel_id"]))) != meta["cast_sha256"]:
            raise WorkflowError("Recover the actual original Brutalize source cast")


def _targets(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, channel: int
) -> list[dict[str, Any]]:
    cast = _cast(game, c, state, channel)
    result = []
    bound = profiles(c, game.store.campaign_id)
    own = resolve(state, actor, bound)
    for role in cast.roles:
        target = role.actor
        if target == actor:
            continue
        if target.kind == "npc":
            from girlframe.engine import m3_npc_guard as guard
            from girlframe.engine.m3_sprite import candidates
            from girlframe.services.m3_npc_guard import prove_assessment

            fact = guard.assessment(state, target)
            if not guard.supported(state, target, actor, cast) or fact is None:
                continue
            if candidates(state, target, actor, bound):
                continue
            try:
                registry = Access(game.store).registry
                assert registry is not None
                registry.require_available("npc.npc.guard")
                prove_assessment(c, game, state, target, fact.id)
            except (ValueError, WorkflowError):
                continue
            result.append(
                dict(
                    ref=target.model_dump(mode="json"),
                    token=target.token,
                    label=resolve(state, target, bound).label,
                )
            )
            continue
        if target.kind != "pilot":
            continue
        other = resolve(state, target, bound)
        if (
            other.inside_frame is None
            or state.sheets[target.entity].medical_state != "fit"
            or not any(x.family == "girl" and not x.damaged for x in other.assets)
            or own.cell is not None
            and other.cell is not None
            and own.cell != other.cell
        ):
            continue
        result.append(
            dict(ref=target.model_dump(mode="json"), token=target.token, label=other.label)
        )
    return result


def preview(game: GameService, viewer: GuildViewer, channel: int) -> dict[str, Any]:
    try:
        with game.store.engine.connect() as c:
            authorize(game, c, viewer)
            state = load_state(c, game.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            if not has_rule(state.sheets[actor.entity], rules.RULE, "ALPHA"):
                return dict(available=False, targets=[])
            targets = _targets(game, c, state, actor, channel)
            return dict(available=bool(targets), targets=targets)
    except (ValueError, WorkflowError):
        return dict(available=False, targets=[])


def controlled_source(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> HighDirection | None:
    """Retain the actual Alpha performer; the Princess owns only her one Play decisions."""
    if not action["data"].get("princess_child"):
        return None
    from girlframe.engine.m3_princess_sex import get as princess_session
    from girlframe.services.m3_princess_sex import _bound

    value = _bound(game, c, state, action)
    meta = action["data"]["alpha"]
    if (
        value is None
        or value.play != "brutalize"
        or meta.get("princess_direction") != value.id
        or meta["actor"] != value.actor.model_dump(mode="json")
        or meta["actor_controller"] != value.actor_controller
        or value.target is None
        or value.target.kind not in ("pilot", "npc")
        or meta["target"] != value.target.model_dump(mode="json")
    ):
        raise WorkflowError("Preserve this original Alpha, real target and fixed Princess author")
    cast = princess_session(state, value.session).cast
    if (
        meta["cast"] != cast.model_dump(mode="json")
        or not any(
            role.actor == value.target and role.controller == meta["target_controller"]
            for role in cast.roles
        )
        or (value.target.kind == "npc" and not meta.get("npc_assessment"))
    ):
        raise WorkflowError("Preserve the original recipient, source cast and NPC assessment")
    if value.target.kind == "npc":
        from girlframe.services.m3_handler_advancements import _history
        from girlframe.services.m3_npc_guard import prove_assessment

        prove_assessment(
            c,
            game,
            _history(c, game, value.bound_event or ""),
            value.target,
            meta["npc_assessment"],
        )
    return value


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    *,
    channel: int,
) -> dict[str, Any]:
    authorize(game, c, viewer)
    from girlframe.services.m3_princess_sex import child_source

    directed = child_source(game, c, viewer, state, prepared, channel)
    actor = (
        ActorRef.model_validate(directed["actor"])
        if directed
        else current_ref(state, viewer.user_id)
    )
    owner = int(directed["actor_controller"]) if directed else viewer.user_id
    target = prepared.target_actor
    from girlframe.services.m3_required_plays import direct_nomination

    nominated = direct_nomination(game, c, state, actor, prepared, channel)
    if (
        not has_rule(state.sheets[actor.entity], rules.RULE, "ALPHA")
        or target is None
        or target.model_dump(mode="json")
        not in [x["ref"] for x in _targets(game, c, state, actor, channel)]
    ):
        raise WorkflowError(
            "Choose your actual Brutalize and another original Girl with known cockpit context"
        )
    if (
        prepared.target is not None
        or (prepared.source_work and not nominated and directed is None)
        or prepared.off_duty_id
        or prepared.order_id
    ):
        raise WorkflowError("Use only the actual Brutalize target in this source scene")
    if not prepared.context.strip() or not prepared.trigger_confirmed:
        raise WorkflowError(
            "Describe the actual tearing into this person with words, fists and teeth"
        )
    cast = _cast(game, c, state, channel)
    if not any(x.actor == actor and x.controller == owner for x in cast.roles):
        raise WorkflowError("Join as the actual original Alpha")
    assert game.store.policy.m3_approval is not None
    other = resolve(state, target, profiles(c, game.store.campaign_id))
    assessment = None
    if target.kind == "npc":
        from girlframe.engine.m3_npc_guard import assessment as guard_assessment

        fact = guard_assessment(state, target)
        assert fact is not None
        assessment = fact.id
    result = dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        actor_controller=owner,
        target_controller=other.controller,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted(
            {x.controller for x in cast.roles}
            | ({cast.facilitator} if cast.facilitator is not None else set())
        ),
        registry=game.store.policy.m3_approval.registry_sha256,
        phase="unrolled",
        followups=[],
        npc_assessment=assessment,
    )
    if directed is not None:
        result["princess_direction"] = directed["direction"]
    return result


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    actor, target = _refs(action)
    direction = controlled_source(game, c, state, action)
    if direction is not None:
        from girlframe.services.m3_princess_sex import pre_roll_child

        if viewer.user_id != direction.author_controller:
            raise WorkflowError("Only the original Princess owns this directed Brutalize roll")
        pre_roll_child(game, c, state, action)
    if action["data"].get("alpha_counter_source"):
        brutalize_counter(
            game,
            c,
            state,
            actor,
            PlayInput.model_validate(action["data"]["prepared"]),
            int(action["channel_id"]),
            action,
        )
    if not has_rule(state.sheets[actor.entity], rules.RULE, "ALPHA") or target.model_dump(
        mode="json"
    ) not in [x["ref"] for x in _targets(game, c, state, actor, int(action["channel_id"]))]:
        raise WorkflowError("Recover the actual original Alpha/target before spending or rolling")
    if target.kind == "npc":
        from girlframe.services.m3_npc_guard import prove_assessment

        prove_assessment(c, game, state, target, action["data"]["alpha"]["npc_assessment"])


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["alpha"]
    meta["phase"] = "choosing"
    level = action["data"]["result"]["tier"]
    game.request(
        c,
        action,
        meta["target_controller"] if level == "low" else meta["actor_controller"],
        "alpha_low"
        if level == "low"
        else ("alpha_npc_damage" if _refs(action)[1].kind == "npc" else "alpha_damage"),
    )


def projection(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    actor, target = _refs(action)
    if target.kind == "npc":
        from girlframe.engine.m3_npc_guard import supported, unarmed

        return dict(
            assets=[],
            npc=True,
            can_counter=supported(
                state,
                target,
                actor,
                SceneCast.model_validate_json(json.dumps(action["data"]["alpha"]["cast"])),
            ),
            unarmed=unarmed(state, target),
            actor=actor.model_dump(mode="json"),
            target=target.model_dump(mode="json"),
        )
    own = state.sheets[target.entity]
    return dict(
        assets=[
            dict(id=x.id, label=x.name if not x.concealed else "Undisclosed Girl Asset")
            for x in own.assets
            if x.family == "girl" and not x.damaged
        ],
        can_counter=not is_helpless(state, target) and own.medical_state == "fit",
        target=action["data"]["alpha"]["target"],
        actor=action["data"]["alpha"]["actor"],
        counter_plays=counter_plays(game, c, state, action, target),
    )


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    actor, target = _refs(action)
    meta = action["data"]["alpha"]
    event = action["data"]["response_event"]
    if any(
        (
            answer.denied,
            answer.text if request["kind"] != "alpha_npc_damage" else False,
            answer.fields,
            answer.number is not None,
            answer.flag is not None,
            answer.member is not None,
        )
    ):
        raise WorkflowError("Use only this actual printed Brutalize choice")
    if request["kind"] in ("alpha_npc_damage", "alpha_npc_mercy"):
        if target.kind != "npc" or state.world is None:
            raise WorkflowError("Use the actual original NPC outcome")
        npc = next(x for x in state.world.npcs if x.id == target.entity and x.alive)
        high = action["data"]["result"]["tier"] == "high"
        if request["kind"] == "alpha_npc_mercy":
            from girlframe.services.m3_npc_guard import prove_assessment

            fact = prove_assessment(c, game, state, target, meta["npc_assessment"])
            if not fact.unarmed or answer.options not in (("kill",), ("spare",)):
                raise WorkflowError("Only the actually reviewed unarmed NPC may be killed anyway")
            kill = answer.options == ("kill",)
        else:
            kill = high
            if answer.options != (("kill",) if high else ("injure",)):
                raise WorkflowError("Apply only the printed actual NPC injury or death")
            if not high and (not answer.text.strip() or len(answer.text) > 120):
                raise WorkflowError("Describe the actual injury you inflict on this NPC")
        if kill:
            from girlframe.engine.m3_battle import end_actor_casts
            from girlframe.engine.m3_physical import interrupt_journeys

            npc = npc.model_copy(update={"alive": False})
            _copy(state, interrupt_journeys(state, target, event, "Actual Brutalize death"))
            _copy(state, end_actor_casts(state, target, event))
        elif request["kind"] == "alpha_npc_damage":
            from girlframe.engine.m3_world_state import WorldTag

            npc = npc.model_copy(
                update={
                    "tags": npc.tags
                    + (
                        WorldTag(
                            id=action["id"] + ":injury",
                            label=answer.text.strip(),
                            giver_entity=actor.model_dump_json(),
                        ),
                    )
                }
            )
            _copy(state, rules.inflict(state, target, actor, action["id"], event))
        assert state.world is not None
        state.world = state.world.model_copy(
            update={"npcs": tuple(npc if x.id == npc.id else x for x in state.world.npcs)}
        )
        state.facts.append(
            dict(
                kind="alpha_npc_outcome",
                event=event,
                action=action["id"],
                target=target.model_dump_json(),
                killed=str(kill),
                injury=answer.text.strip(),
            )
        )
        meta.update(phase="resolved", effect_event=event)
    elif request["kind"] == "alpha_damage":
        from girlframe.services.m3_battle import damage_actor

        if len(answer.options) != 1 or answer.options[0] not in {
            x.id for x in state.sheets[target.entity].assets if x.family == "girl" and not x.damaged
        }:
            raise WorkflowError("Choose one actual intact Girl Asset of the original target")
        changed, work = damage_actor(
            game,
            c,
            state,
            target=target,
            asset_id=answer.options[0],
            source_action=action["id"],
            source_work=None,
            event=event,
            actor=actor,
            opponent=actor,
            chooser_controller=meta["actor_controller"],
            occurrence="brutalize",
            physical_blow=True,
        )
        if action["data"]["result"]["tier"] == "mid":
            changed = rules.inflict(changed, target, actor, action["id"], event)
            action["data"]["result"]["broken"] = True
        else:
            changed = make_helpless(changed, target, actor, event)
            action["data"]["result"]["helpless"] = True
        _copy(state, changed)
        meta.update(phase="effects", effect_event=event)
        meta["followups"].extend(work)
    elif request["kind"] == "alpha_low":
        if len(answer.options) != 1 or answer.options[0] not in (
            "pass",
            "counter_broken",
            "counter_only",
        ):
            raise WorkflowError("Choose your actual one opportunity or explicitly pass it")
        if answer.options[0] == "pass":
            _after_counter(game, c, state, action)
        else:
            if target.kind == "pilot" and (
                is_helpless(state, target) or state.sheets[target.entity].medical_state != "fit"
            ):
                raise WorkflowError("This actual condition prevents an ordinary counter Play")
            meta.update(
                phase="counter",
                retaliate=answer.options[0] == "counter_broken",
                counter_selected_event=event,
                selection_choice=request["id"],
            )
            game.request(
                c,
                action,
                meta["target_controller"],
                "alpha_counter_play",
                dict(actor=meta["target"], attacker=meta["actor"]),
            )
    else:
        raise WorkflowError("Start the actual owned counter Play; acknowledgment cannot replace it")


def _finish(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    if action["state"] in ("complete", "aborted") or game.pending(c, action["id"]):
        return
    action["data"]["alpha"]["phase"] = "complete"
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def _after_counter(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"]["alpha"]
    _, target = _refs(action)
    if target.kind == "npc":
        from girlframe.services.m3_npc_guard import prove_assessment

        fact = prove_assessment(c, game, state, target, meta["npc_assessment"])
        if fact.unarmed:
            meta["phase"] = "mercy"
            game.request(c, action, meta["actor_controller"], "alpha_npc_mercy")
            return
    meta["phase"] = "resolved"


def npc_counter_context(
    game: GameService, c: Connection, parent: str, choice: str
) -> tuple[GameState, ActorRef, ActorRef, SceneCast]:
    action = game.action(c, parent)
    meta = action["data"].get("alpha")
    row = next((x for x in game.pending(c, parent) if x["id"] == choice), None)
    if (
        meta is None
        or meta.get("phase") != "counter"
        or action["data"].get("result", {}).get("tier") != "low"
        or row is None
        or row["kind"] != "alpha_counter_play"
        or row["actor_id"] != str(meta["target_controller"])
    ):
        raise WorkflowError("Recover the actual original pending low NPC opportunity")
    attacker, npc = _refs(action)
    state = load_state(c, game.store.campaign_id)
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    from girlframe.engine.m3_npc_guard import supported
    from girlframe.services.m3_npc_guard import prove_assessment

    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == parent,
        )
    )
    selected = c.scalar(
        sa.select(t.m2["m2_responses"].c.answer_json).where(
            t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_responses"].c.choice_id == meta["selection_choice"],
            t.m2["m2_responses"].c.event_id == meta["counter_selected_event"],
            t.m2["m2_responses"].c.actor_id == str(meta["target_controller"]),
        )
    )
    expected = "counter_broken" if meta["retaliate"] else "counter_only"
    if (
        npc.kind != "npc"
        or not supported(state, npc, attacker, cast)
        or fingerprint(_cast(game, c, state, int(action["channel_id"]))) != meta["cast_sha256"]
        or receipt is None
        or json.loads(receipt) != action["data"].get("receipt")
        or selected is None
        or ChoiceAnswer.model_validate_json(selected).options != (expected,)
    ):
        raise WorkflowError("Preserve the real original Guard, low receipt and owned opportunity")
    prove_assessment(c, game, state, npc, meta["npc_assessment"])
    return state, npc, attacker, cast


def complete_npc_counter(
    game: GameService, c: Connection, parent: str, choice: str, npc: ActorRef, event: str
) -> None:
    from girlframe.services.m3_npc_guard import prove_performed

    state, original, attacker, _ = npc_counter_context(game, c, parent, choice)
    if npc != original:
        raise WorkflowError("Only this actual original Guard may complete its counter")
    prove_performed(c, game, event, parent, choice, npc, attacker)
    action = game.action(c, parent)
    meta = action["data"]["alpha"]
    actual = str(uuid4())
    if meta["retaliate"]:
        state = rules.inflict(state, attacker, npc, parent, actual, counter=event)
    rows = t.m2["m2_choices"]
    c.execute(
        rows.update()
        .where(
            rows.c.campaign_id == game.store.campaign_id,
            rows.c.id == choice,
            rows.c.state == "pending",
        )
        .values(state="completed_by_work", revision=rows.c.revision + 1)
    )
    meta.update(counter_completed_event=actual, counter_performed_event=event)
    _after_counter(game, c, state, action)
    _finish(game, c, state, action)
    audit = c.execute(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == event,
        )
    ).scalar_one()
    game.event(
        c,
        audit,
        str(uuid4()),
        "m3.alpha_npc_counter_completed",
        state,
        event_id=actual,
        action_id=parent,
        source_event=event,
    )
    game.save_action(c, action)
    if action["state"] == "complete" and action["data"].get("princess_child"):
        complete_directed(game, c, action, actual)


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    meta = action["data"]["alpha"]
    if meta["phase"] == "effects" and not meta.get("materialized"):
        from girlframe.services.m3_battle import synchronize_damage

        synchronize_damage(game, c, event)
        current = game.action(c, action["id"])
        action.clear()
        action.update(current)
        action["data"]["alpha"]["materialized"] = event
    if action["data"]["alpha"]["phase"] in ("effects", "resolved"):
        _finish(game, c, load_state(c, game.store.campaign_id), action)
        if action["state"] == "complete" and action["data"].get("alpha_counter_source"):
            synchronize_counters(game, c, event)
            current = game.action(c, action["id"])
            action.clear()
            action.update(current)
        if action["state"] == "complete" and action["data"].get("princess_child"):
            complete_directed(game, c, action, event)
        if action["state"] == "complete" and action["data"].get("battle_counter_source"):
            from girlframe.services.m3_battle import complete_counter_play

            complete_counter_play(game, c, action, event, None, str(uuid4()))


def _directed_completion_author(
    game: GameService, c: Connection, action: dict[str, Any], event: str
) -> int:
    """Accept only this Brutalize's real result, damage work or completed counter."""
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if audit is None or audit["actor_id"] is None:
        raise WorkflowError("Recover the actual directed Brutalize completion cause")
    payload = json.loads(audit["payload_json"])
    meta = action["data"]["alpha"]
    choices = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == payload.get("choice_id"),
                choices.c.action_id == action["id"],
                choices.c.state == "answered",
                choices.c.kind.in_(
                    ("alpha_damage", "alpha_low", "alpha_npc_damage", "alpha_npc_mercy")
                ),
            )
        )
        .mappings()
        .first()
    )
    if (
        audit["kind"] in ("m2.choice_resolved", "m3.choice_resolved")
        and payload.get("action_id") == action["id"]
        and row is not None
    ):
        expected = (
            str(meta["target_controller"])
            if row["kind"] == "alpha_low"
            else str(action["data"]["princess_child"]["author"])
        )
        if audit["actor_id"] == expected:
            return int(audit["actor_id"])
    if (
        audit["kind"] == "m3.alpha_counter_completed"
        and payload.get("action_id") == action["id"]
        and meta.get("counter_completed_event") == event
        and payload.get("child") == meta.get("counter_child")
        and meta.get("counter_child")
    ):
        counter = game.action(c, meta["counter_child"])
        if (
            counter["state"] == "complete"
            and counter["parent_id"] == action["id"]
            and counter["actor_id"] == str(meta["target_controller"])
            and counter["data"].get("alpha_counter_completed") == event
            and counter["data"].get("receipt")
            and not game.pending(c, counter["id"])
        ):
            return int(audit["actor_id"])
    if (
        audit["kind"] == "m3.alpha_npc_counter_completed"
        and payload.get("action_id") == action["id"]
        and meta.get("counter_completed_event") == event
        and payload.get("source_event") == meta.get("counter_performed_event")
        and meta.get("counter_performed_event")
        and audit["actor_id"] == str(meta["target_controller"])
    ):
        from girlframe.services.m3_npc_guard import prove_performed

        npc_counter = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.action_id == action["id"],
                    choices.c.kind == "alpha_counter_play",
                    choices.c.actor_id == str(meta["target_controller"]),
                    choices.c.state == "completed_by_work",
                )
            )
            .mappings()
            .one_or_none()
        )
        if npc_counter is not None:
            actor, npc = _refs(action)
            prove_performed(
                c,
                game,
                meta["counter_performed_event"],
                action["id"],
                npc_counter["id"],
                npc,
                actor,
            )
            return int(audit["actor_id"])
    work = t.m3["m3_required_work"]
    if meta.get("followups") and c.scalar(
        sa.select(work.c.id)
        .where(
            work.c.campaign_id == game.store.campaign_id,
            work.c.id.in_(meta["followups"]),
            work.c.state == "resolved",
            work.c.event_id == event,
        )
        .limit(1)
    ):
        return int(audit["actor_id"])
    raise WorkflowError("Preserve this Brutalize's actual completed result and owned consequences")


def complete_directed(
    game: GameService, c: Connection, action: dict[str, Any], trigger: str
) -> None:
    from girlframe.engine import m3_princess_sex as princess
    from girlframe.services.m3_princess_sex import complete_child

    child = game.action(c, action["id"])
    if not child["data"].get("princess_child") or child["state"] != "complete":
        return
    state = load_state(c, game.store.campaign_id)
    direction = princess.direction(state, child["data"]["princess_child"]["direction"])
    if direction.completed_event:
        return
    controlled_source(game, c, state, child)
    human = _directed_completion_author(game, c, child, trigger)
    event = str(uuid4())
    complete_child(game, c, state, child, event)
    game.event(
        c,
        human,
        str(uuid4()),
        "m3.princess_directed_brutalize_completed",
        state,
        event_id=event,
        action_id=child["id"],
        parent=direction.parent,
        direction=direction.id,
        trigger_event=trigger,
    )
    from girlframe.services.m3_princess_sex import synchronize as synchronize_princess

    synchronize_princess(game, c, child, event)


def prove_directed_completion(
    game: GameService, c: Connection, value: HighDirection, audit: RowMapping
) -> None:
    payload = json.loads(audit["payload_json"])
    child = game.action(c, value.child or "")
    meta = child["data"].get("alpha", {})
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == child["id"],
        )
    )
    if (
        value.play != "brutalize"
        or audit["kind"] != "m3.princess_directed_brutalize_completed"
        or payload.get("action_id") != child["id"]
        or payload.get("parent") != value.parent
        or payload.get("direction") != value.id
        or child["parent_id"] != value.parent
        or child["actor_id"] != value.actor.entity
        or child["data"].get("play") != value.play
        or meta.get("princess_direction") != value.id
        or meta.get("actor") != value.actor.model_dump(mode="json")
        or meta.get("actor_controller") != value.actor_controller
        or value.target is None
        or meta.get("target") != value.target.model_dump(mode="json")
        or (child["data"].get("princess_child") or {}).get("author") != value.author_controller
        or child["state"] != "complete"
        or receipt is None
        or json.loads(receipt) != child["data"].get("receipt")
        or game.pending(c, child["id"])
    ):
        raise WorkflowError("Prove this actual directed Brutalize and its immutable receipt")
    from girlframe.engine.m3_princess_sex import get as princess_session
    from girlframe.services.m3_handler_advancements import _history

    bound = _history(c, game, value.bound_event or "")
    cast = princess_session(bound, value.session).cast
    if meta.get("cast") != cast.model_dump(mode="json") or not any(
        role.actor == value.target and role.controller == meta.get("target_controller")
        for role in cast.roles
    ):
        raise WorkflowError("Prove the original directed Brutalize recipient and controller")
    if value.target.kind == "npc":
        from girlframe.services.m3_npc_guard import prove_assessment

        prove_assessment(c, game, bound, value.target, meta.get("npc_assessment", ""))
    if int(audit["actor_id"]) != _directed_completion_author(
        game, c, child, payload.get("trigger_event", "")
    ):
        raise WorkflowError("Retain the actual human author of the completed Brutalize consequence")


def advice_counter(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    prepared: PlayInput,
    channel: int,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The native original target may answer Brutalize with advice to its attacker."""
    from girlframe.engine import m3_oldgen as oldgen
    from girlframe.engine.m3_alpha_sex import asleep
    from girlframe.services.m3_access import load_registry
    from girlframe.services.m3_dose_up import _native

    if prepared.play != oldgen.PLAY or prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    meta = parent["data"].get("alpha")
    if meta is None:
        return None
    if fingerprint(_cast(game, c, state, channel)) != meta["cast_sha256"]:
        raise WorkflowError("Recover the original Brutalize counter scene and people")
    attacker, target = _refs(parent)
    row = next(
        (x for x in game.pending(c, parent["id"]) if x["kind"] == "alpha_counter_play"), None
    )
    if (
        actor != target
        or target.kind != "pilot"
        or attacker.kind != "pilot"
        or state.sheets[actor.entity].girl != "OLDGEN"
        or not has_rule(state.sheets[actor.entity], oldgen.ADVICE, "OLDGEN")
        or meta.get("phase") != "counter"
        or row is None
        or row["actor_id"] != actor.entity
        or prepared.target != int(attacker.entity)
        or prepared.target_actor is not None
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or int(parent["channel_id"]) != channel
        or is_helpless(state, actor)
        or asleep(state, actor)
        or asleep(state, attacker)
    ):
        raise WorkflowError("Use the native original Oldgen's advice to this awake Alpha attacker")
    for person in (actor, attacker):
        _native(game, c, state, person)
    load_registry().require_available(oldgen.ADVICE)
    selection = c.scalar(
        sa.select(t.m2["m2_responses"].c.answer_json).where(
            t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_responses"].c.choice_id == meta.get("selection_choice"),
            t.m2["m2_responses"].c.event_id == meta.get("counter_selected_event"),
            t.m2["m2_responses"].c.actor_id == actor.entity,
        )
    )
    expected = "counter_broken" if meta["retaliate"] else "counter_only"
    if selection is None or ChoiceAnswer.model_validate_json(selection).options != (expected,):
        raise WorkflowError("Recover the original target's actual selected Brutalize opportunity")
    scope = dict(
        choice=row["id"], actor=meta["target"], attacker=meta["actor"], parent=parent["id"]
    )
    if action is not None and (
        action["data"].get("alpha_counter_source") != scope
        or action["parent_id"] != parent["id"]
        or action["actor_id"] != actor.entity
        or action["data"]["prepared"] != prepared.model_dump(mode="json")
    ):
        raise WorkflowError("Recover this exact original advice counter before spending or rolling")
    return scope


def brutalize_counter(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    prepared: PlayInput,
    channel: int,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The actual native Alpha target answers her attacker with her own Brutalize."""
    from girlframe.engine.m3_alpha_sex import asleep
    from girlframe.services.m3_access import load_registry
    from girlframe.services.m3_dose_up import _native

    if prepared.play != "brutalize" or prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    meta = parent["data"].get("alpha")
    if meta is None:
        return None
    attacker, target = _refs(parent)
    row = next(
        (x for x in game.pending(c, parent["id"]) if x["kind"] == "alpha_counter_play"), None
    )
    if (
        actor != target
        or target.kind != "pilot"
        or attacker.kind != "pilot"
        or current_ref(state, int(target.entity)) != target
        or current_ref(state, int(attacker.entity)) != attacker
        or state.sheets[actor.entity].girl != "ALPHA"
        or not has_rule(state.sheets[actor.entity], rules.RULE, "ALPHA")
        or meta.get("phase") != "counter"
        or parent["data"].get("result", {}).get("tier") != "low"
        or row is None
        or row["actor_id"] != actor.entity
        or prepared.target_actor != attacker
        or prepared.target is not None
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or int(parent["channel_id"]) != channel
        or fingerprint(_cast(game, c, state, channel)) != meta["cast_sha256"]
        or is_helpless(state, actor)
        or asleep(state, actor)
        or asleep(state, attacker)
    ):
        raise WorkflowError("Use the native original Alpha's own Brutalize against her attacker")
    for person in (actor, attacker):
        _native(game, c, state, person)
    if attacker.model_dump(mode="json") not in [
        x["ref"] for x in _targets(game, c, state, actor, channel)
    ]:
        raise WorkflowError("Recover the original attacker's actual legal Brutalize target")
    load_registry().require_available(rules.RULE)
    responses, choices, receipts = (t.m2[x] for x in ("m2_responses", "m2_choices", "m2_receipts"))
    selection = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                responses.c.campaign_id == choices.c.campaign_id,
                responses.c.choice_id == choices.c.id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.choice_id == meta.get("selection_choice"),
            responses.c.event_id == meta.get("counter_selected_event"),
            responses.c.actor_id == actor.entity,
            choices.c.action_id == parent["id"],
            choices.c.kind == "alpha_low",
        )
    )
    receipt = c.scalar(
        sa.select(receipts.c.body_json).where(
            receipts.c.campaign_id == game.store.campaign_id,
            receipts.c.action_id == parent["id"],
        )
    )
    expected = "counter_broken" if meta["retaliate"] else "counter_only"
    if (
        selection is None
        or ChoiceAnswer.model_validate_json(selection).options != (expected,)
        or receipt is None
        or json.loads(receipt) != parent["data"].get("receipt")
    ):
        raise WorkflowError("Recover the original low receipt and owned counter selection")
    scope = dict(
        choice=row["id"], actor=meta["target"], attacker=meta["actor"], parent=parent["id"]
    )
    if action is not None and (
        action["data"].get("alpha_counter_source") != scope
        or action["parent_id"] != parent["id"]
        or action["actor_id"] != actor.entity
        or action["data"]["prepared"] != prepared.model_dump(mode="json")
        or action["data"].get("alpha", {}).get("actor") != meta["target"]
        or action["data"].get("alpha", {}).get("target") != meta["actor"]
    ):
        raise WorkflowError(
            "Recover this exact original Brutalize counter before spending or rolling"
        )
    return scope


def self_dose_counter(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    prepared: PlayInput,
    channel: int,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The actual native Stim answers failed Brutalize with her own self-Dose."""
    from girlframe.engine import m3_dose_up as dose
    from girlframe.engine.m3_alpha_sex import asleep
    from girlframe.services.m3_access import load_registry
    from girlframe.services.m3_dose_up import _native, _operator

    if prepared.play != dose.PLAY or prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    meta = parent["data"].get("alpha")
    if meta is None:
        return None
    attacker, target = _refs(parent)
    row = next(
        (x for x in game.pending(c, parent["id"]) if x["kind"] == "alpha_counter_play"), None
    )
    if (
        actor != target
        or target.kind != "pilot"
        or attacker.kind != "pilot"
        or current_ref(state, int(target.entity)) != target
        or current_ref(state, int(attacker.entity)) != attacker
        or state.sheets[actor.entity].girl != "STIM-BLISSED"
        or not has_rule(state.sheets[actor.entity], dose.RULE, "STIM-BLISSED")
        or meta.get("phase") != "counter"
        or parent["data"].get("result", {}).get("tier") != "low"
        or row is None
        or row["actor_id"] != actor.entity
        or prepared.target_actor not in (None, actor)
        or prepared.target is not None
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or int(parent["channel_id"]) != channel
        or fingerprint(_cast(game, c, state, channel)) != meta["cast_sha256"]
        or is_helpless(state, actor)
        or asleep(state, actor)
        or asleep(state, attacker)
    ):
        raise WorkflowError(
            "Use the native original Stim's own self-Dose in this Brutalize opportunity"
        )
    for person in (actor, attacker):
        _native(game, c, state, person)
    _operator(game, c, state, actor)
    load_registry().require_available(dose.RULE)
    responses, choices, receipts = (t.m2[x] for x in ("m2_responses", "m2_choices", "m2_receipts"))
    selection = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                responses.c.campaign_id == choices.c.campaign_id,
                responses.c.choice_id == choices.c.id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.choice_id == meta.get("selection_choice"),
            responses.c.event_id == meta.get("counter_selected_event"),
            responses.c.actor_id == actor.entity,
            choices.c.action_id == parent["id"],
            choices.c.kind == "alpha_low",
        )
    )
    receipt = c.scalar(
        sa.select(receipts.c.body_json).where(
            receipts.c.campaign_id == game.store.campaign_id,
            receipts.c.action_id == parent["id"],
        )
    )
    expected = "counter_broken" if meta["retaliate"] else "counter_only"
    if (
        selection is None
        or ChoiceAnswer.model_validate_json(selection).options != (expected,)
        or receipt is None
        or json.loads(receipt) != parent["data"].get("receipt")
    ):
        raise WorkflowError("Recover the original low receipt and owned counter selection")
    scope = dict(
        choice=row["id"], actor=meta["target"], attacker=meta["actor"], parent=parent["id"]
    )
    if action is not None and (
        action["data"].get("alpha_counter_source") != scope
        or action["parent_id"] != parent["id"]
        or action["actor_id"] != actor.entity
        or action["data"]["prepared"] != prepared.model_dump(mode="json")
        or action["data"].get("dose_up", {}).get("actor") != meta["target"]
        or action["data"].get("dose_up", {}).get("target") != meta["target"]
    ):
        raise WorkflowError(
            "Recover this exact original self-Dose counter before spending or rolling"
        )
    return scope


def counter_plays(
    game: GameService, c: Connection, state: GameState, parent: dict[str, Any], actor: ActorRef
) -> tuple[str, ...]:
    from girlframe.engine import m3_oldgen as oldgen
    from girlframe.services.m3_alpha_beneath import counter as beneath_counter
    from girlframe.services.m3_alpha_doll import counter as doll_counter
    from girlframe.services.m3_alpha_easy_target import counter as easy_counter
    from girlframe.services.m3_alpha_flirt import counter as flirt_counter

    attacker, _ = _refs(parent)
    plays = ["keep_your_head"]
    if attacker.kind != "pilot":
        return tuple(plays)
    for play, validate, target in (
        ("flirt", flirt_counter, dict(target=int(attacker.entity))),
        ("put_someone_beneath_you", beneath_counter, dict(target=int(attacker.entity))),
        (oldgen.PLAY, advice_counter, dict(target=int(attacker.entity))),
        ("brutalize", brutalize_counter, dict(target_actor=attacker)),
        ("dose_up", self_dose_counter, {}),
        ("easy_target", easy_counter, {}),
        ("unassuming_doll", doll_counter, dict(target_actor=attacker)),
    ):
        try:
            source = validate(
                game,
                c,
                state,
                actor,
                PlayInput(
                    play=play,
                    parent=parent["id"],
                    **target,
                    context="Availability preview only; no actual performance or action",
                    trigger_confirmed=True,
                    heat=0,
                ),
                int(parent["channel_id"]),
            )
        except (ValueError, WorkflowError):
            continue
        if source is not None:
            plays.append(play)
    return tuple(plays)


def validate_counter_child(
    game: GameService, c: Connection, parent: dict[str, Any], actor: ActorRef, prepared: PlayInput
) -> dict[str, Any]:
    from girlframe.services.m3_alpha_beneath import counter as beneath_counter
    from girlframe.services.m3_alpha_doll import counter as doll_counter
    from girlframe.services.m3_alpha_easy_target import counter as easy_counter
    from girlframe.services.m3_alpha_flirt import counter as flirt_counter

    if prepared.play in (
        "flirt",
        "put_someone_beneath_you",
        "old_dog_new_pups",
        "brutalize",
        "dose_up",
        "easy_target",
        "unassuming_doll",
    ):
        validate = {
            "flirt": flirt_counter,
            "put_someone_beneath_you": beneath_counter,
            "old_dog_new_pups": advice_counter,
            "brutalize": brutalize_counter,
            "dose_up": self_dose_counter,
            "easy_target": easy_counter,
            "unassuming_doll": doll_counter,
        }[prepared.play]
        source = validate(
            game,
            c,
            load_state(c, game.store.campaign_id),
            actor,
            prepared,
            int(parent["channel_id"]),
        )
        if source is None or source["parent"] != parent["id"]:
            raise WorkflowError("Recover the actual original source-specific Brutalize counter")
        return source
    meta = parent["data"].get("alpha")
    if (
        meta is None
        or meta.get("phase") != "counter"
        or meta["target"] != actor.model_dump(mode="json")
        or prepared.play != "keep_your_head"
        or prepared.target is not None
        or prepared.target_actor is not None
        or prepared.parent != parent["id"]
        or prepared.source_work
    ):
        raise WorkflowError(
            "This source supports the original target's genuine Keep Your Head counter"
        )
    row = next(
        (
            x
            for x in game.pending(c, parent["id"])
            if x["kind"] == "alpha_counter_play" and x["actor_id"] == str(meta["target_controller"])
        ),
        None,
    )
    if row is None:
        raise WorkflowError("Recover the actual original pending counter opportunity")
    return dict(choice=row["id"], actor=meta["target"], attacker=meta["actor"], parent=parent["id"])


def synchronize_counters(game: GameService, c: Connection, event: str) -> GameState | None:
    actions = t.m2["m2_actions"]
    rows = (
        c.execute(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == game.store.campaign_id,
                actions.c.state == "complete",
                sa.func.json_extract(actions.c.body_json, "$.alpha_counter_source").is_not(None),
                sa.func.json_extract(actions.c.body_json, "$.alpha_counter_completed").is_(None),
            )
        )
        .scalars()
        .all()
    )
    for identity in rows:
        child = game.action(c, identity)
        if (
            child["data"].get("ankou_feedback")
            and child["data"].get("play")
            in (
                "brutalize",
                "unassuming_doll",
                "easy_target",
                "old_dog_new_pups",
                "dose_up",
                "keep_your_head",
                "flirt",
                "put_someone_beneath_you",
            )
            and child["data"].get("result", {}).get("blocked_before_roll")
        ):
            from girlframe.services.m3_ankou_alpha_counter import finish_ended

            finish_ended(game, c, load_state(c, game.store.campaign_id), child, event)
            continue
        source = child["data"]["alpha_counter_source"]
        parent = game.action(c, source["parent"])
        meta = parent["data"]["alpha"]
        actor, target = _refs(parent)
        if (
            child["parent_id"] != parent["id"]
            or child["actor_id"] != target.entity
            or child["data"]["play"]
            not in (
                "keep_your_head",
                "flirt",
                "put_someone_beneath_you",
                "old_dog_new_pups",
                "brutalize",
                "dose_up",
                "easy_target",
                "unassuming_doll",
            )
            or child["data"]["character_ids"].get(target.entity) != target.incarnation
            or source["actor"] != meta["target"]
            or source["attacker"] != meta["actor"]
            or not child["data"].get("receipt")
            or game.pending(c, child["id"])
        ):
            raise WorkflowError(
                "Only the actual original completed counter can resolve this source"
            )
        request = next(
            (
                x
                for x in game.pending(c, parent["id"])
                if x["id"] == source["choice"] and x["kind"] == "alpha_counter_play"
            ),
            None,
        )
        if request is None:
            continue
        responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
        selected = c.scalar(
            sa.select(responses.c.answer_json)
            .join(
                choices,
                sa.and_(
                    responses.c.campaign_id == choices.c.campaign_id,
                    responses.c.choice_id == choices.c.id,
                ),
            )
            .where(
                responses.c.campaign_id == game.store.campaign_id,
                responses.c.event_id == meta["counter_selected_event"],
                responses.c.choice_id == meta["selection_choice"],
                responses.c.actor_id == target.entity,
                choices.c.action_id == parent["id"],
                choices.c.kind == "alpha_low",
            )
        )
        receipt = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == child["id"],
            )
        )
        expected = "counter_broken" if meta["retaliate"] else "counter_only"
        if (
            selected is None
            or ChoiceAnswer.model_validate_json(selected).options != (expected,)
            or receipt is None
            or json.loads(receipt) != child["data"]["receipt"]
        ):
            raise WorkflowError(
                "Preserve the actual original target's selected counter and saved receipt"
            )
        state = load_state(c, game.store.campaign_id)
        if child["data"]["play"] == "flirt":
            from girlframe.services.m3_alpha_flirt import completed as complete_flirt

            if not complete_flirt(game, c, state, child, event):
                continue
        if child["data"]["play"] == "put_someone_beneath_you":
            from girlframe.services.m3_alpha_beneath import completed as complete_beneath

            if not complete_beneath(game, c, state, child, event):
                continue
        if child["data"]["play"] == "brutalize":
            own = child["data"].get("alpha", {})
            prepared = PlayInput.model_validate(child["data"]["prepared"])
            if (
                own.get("phase") != "complete"
                or own.get("actor") != meta["target"]
                or own.get("target") != meta["actor"]
                or own.get("actor_controller") != meta["target_controller"]
                or own.get("target_controller") != meta["actor_controller"]
                or own.get("cast") != meta["cast"]
                or child["data"].get("learned_play")
                or prepared.source_work is not None
                or prepared.parent != parent["id"]
                or prepared.target is not None
                or prepared.target_actor != actor
            ):
                raise WorkflowError("Complete the original native Alpha's actual counter results")
            # This child keeps its own result and chooser. A low result can itself
            # owe a genuine counter; high/mid damage must finish its ordinary work.
            kind = "alpha_low" if child["data"]["result"]["tier"] == "low" else "alpha_damage"
            owner = own["target_controller"] if kind == "alpha_low" else own["actor_controller"]
            result_choice = (
                c.execute(
                    sa.select(choices).where(
                        choices.c.campaign_id == game.store.campaign_id,
                        choices.c.action_id == identity,
                        choices.c.kind == kind,
                    )
                )
                .mappings()
                .one()
            )
            response = (
                c.execute(
                    sa.select(responses).where(
                        responses.c.campaign_id == game.store.campaign_id,
                        responses.c.choice_id == result_choice["id"],
                    )
                )
                .mappings()
                .first()
            )
            if response is None:
                # event() precedes the response insert. Only that actual current
                # choice may wait for the post-response synchronization callback.
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
                    or incoming["actor_id"] != str(owner)
                    or payload.get("action_id") != identity
                    or payload.get("choice_id") != result_choice["id"]
                ):
                    raise WorkflowError("Recover the exact original Brutalize result response")
                continue
            if response["actor_id"] != str(owner) or result_choice["actor_id"] != str(owner):
                raise WorkflowError("Preserve the actual counter result's original chooser")
        if child["data"]["play"] == "old_dog_new_pups":
            from girlframe.engine import m3_oldgen as oldgen
            from girlframe.services.m3_oldgen import prove_advice

            original = next(
                (x for x in oldgen.records(state, oldgen.Advice) if x.id == identity), None
            )
            advice = child["data"].get("oldgen", {})
            if original is None or advice.get("phase") != "complete":
                raise WorkflowError("Complete the actual original advice and owned listening")
            choice = advice.get("listen_choice") if original.total >= 8 else original.choice
            response_event = advice.get("listen_event") if original.total >= 8 else original.event
            response = c.scalar(
                sa.select(responses.c.event_id).where(
                    responses.c.campaign_id == game.store.campaign_id,
                    responses.c.choice_id == choice,
                )
            )
            if response is None:
                # The event is saved before its immutable response. Retry after insertion.
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
                if (
                    response_event != event
                    or incoming["kind"] != "m3.choice_resolved"
                    or incoming["actor_id"] != str(original.counterpart)
                    or payload.get("action_id") != identity
                    or payload.get("choice_id") != choice
                ):
                    raise WorkflowError("Recover the exact current advice response event")
                continue
            proof = prove_advice(game, c, state, identity)
            if (
                proof.actor != target
                or proof.target != actor
                or proof.cast.model_dump(mode="json") != meta["cast"]
                or child["data"].get("learned_play")
                or source
                != advice_counter(
                    game,
                    c,
                    state,
                    target,
                    PlayInput.model_validate(child["data"]["prepared"]),
                    int(parent["channel_id"]),
                    child,
                )
            ):
                raise WorkflowError(
                    "Preserve the actual native advice and original Alpha recipient"
                )
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
                dose.actor != target
                or dose.target != target
                or dose.contact is not None
                or dose.order is not None
                or child["data"]["dose_up"]["phase"] != "complete"
                or child["data"]["prepared"].get("source_work") is not None
                or child["data"]["dose_up"].get("princess_direction") is not None
                or child["data"]["dose_up"].get("required_recipe") is not None
                or dose.cast.model_dump(mode="json") != meta["cast"]
                or child["data"].get("learned_play")
                or source
                != self_dose_counter(
                    game,
                    c,
                    state,
                    target,
                    PlayInput.model_validate(child["data"]["prepared"]),
                    int(parent["channel_id"]),
                    child,
                )
            ):
                raise WorkflowError("Complete the actual original Stim's genuine self-Dose counter")
        if child["data"]["play"] == "easy_target":
            from girlframe.services.m3_alpha_easy_target import completed as complete_easy

            if not complete_easy(game, c, state, child, event):
                continue
        if child["data"]["play"] == "unassuming_doll":
            from girlframe.services.m3_alpha_doll import completed as complete_doll

            if not complete_doll(game, c, state, child, event):
                continue
        actual = str(uuid4())
        if meta["retaliate"]:
            state = rules.inflict(state, actor, target, parent["id"], actual, counter=child["id"])
        choice = t.m2["m2_choices"]
        c.execute(
            choice.update()
            .where(
                choice.c.campaign_id == game.store.campaign_id,
                choice.c.id == request["id"],
                choice.c.state == "pending",
            )
            .values(state="completed_by_work", revision=choice.c.revision + 1)
        )
        child["data"]["alpha_counter_completed"] = actual
        meta.update(phase="resolved", counter_child=child["id"], counter_completed_event=actual)
        game.save_action(c, child)
        _finish(game, c, state, parent)
        audit = c.execute(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        ).scalar_one()
        game.event(
            c,
            audit,
            str(uuid4()),
            "m3.alpha_counter_completed",
            state,
            event_id=actual,
            action_id=parent["id"],
            child=child["id"],
            source_event=event,
        )
        if parent["state"] == "complete" and parent["data"].get("princess_child"):
            complete_directed(game, c, parent, actual)
        if parent["state"] == "complete" and parent["data"].get("battle_counter_source"):
            from girlframe.services.m3_battle import complete_counter_play

            complete_counter_play(game, c, parent, actual, None, str(uuid4()))

    return load_state(c, game.store.campaign_id) if rows else None


def removable(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorRef, ActorRef] | None:
    if action["data"]["play"] != "disobey_orders" or action["data"]["result"].get("tier") != "mid":
        return None
    identity = action["data"]["prepared"].get("order_id")
    orders = t.m2["m2_orders"]
    order = (
        c.execute(
            sa.select(orders).where(
                orders.c.campaign_id == game.store.campaign_id, orders.c.id == identity
            )
        )
        .mappings()
        .first()
    )
    if order is None:
        return None
    if json.loads(order["body_json"]).get("npc_order"):
        if json.loads(order["body_json"])["npc_order"].get("origin_kind", "broken") != "broken":
            return None
        from girlframe.services.m3_npc_orders import removable as npc_removable

        return npc_removable(game, c, state, action)
    originals = c.execute(
        sa.select(t.m2["m2_actions"].c.body_json).where(
            t.m2["m2_actions"].c.campaign_id == game.store.campaign_id,
            sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.order_id") == identity,
            sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.play") == "receive_orders",
        )
    ).scalar_one_or_none()
    if originals is None:
        return None
    ids = json.loads(originals).get("character_ids", {})
    try:
        subject = current_ref(state, int(order["target_id"]))
        inflictor = current_ref(state, int(order["issuer_id"]))
    except ValueError:
        return None
    if (
        ids.get(subject.entity) != subject.incarnation
        or ids.get(inflictor.entity) != inflictor.incarnation
        or str(action["actor_id"]) != subject.entity
        or not rules.conditions(state, subject, inflictor)
    ):
        return None
    return subject, inflictor


def remove_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    if request["kind"] != "actor_disobey" or answer.options != ("remove_broken",):
        return False
    eligible = removable(game, c, state, action)
    if eligible is None or any(
        (
            answer.denied,
            answer.text,
            answer.fields,
            answer.number is not None,
            answer.flag is not None,
            answer.member is not None,
        )
    ):
        raise WorkflowError("Only a real mid Disobey against this actual inflictor removes Broken")
    subject, inflictor = eligible
    changed = rules.remove(
        state, subject, inflictor, action["id"], action["data"]["response_event"]
    )
    state.alpha_broken = changed.alpha_broken
    state.sheets[subject.entity].revision += 1
    action["data"]["result"].update(can_disobey=True, removed_broken=True)
    game.request(c, action, state.handler, "handler_disobey")
    return True
