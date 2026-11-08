"""Persistent basic Handler Plays and narrowly delegated, original-actor counters."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_plays as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import owned_refs, resolve
from girlframe.engine.m3_careers import original_sheet
from girlframe.engine.m3_handler_consequences import active_handler, body_original
from girlframe.engine.m3_handler_play_state import BASIC, Effect, HandlerPlay, Play
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.engine.m3_off_duty import Period
    from girlframe.engine.m3_role_punishment_state import RolePunishment
    from girlframe.services.m2_game import GameService


SOURCE_PROMPTS = {
    "PRINCESS": "Princess: standards and expectations",
    "MOCKINGBIRD": "Mockingbird: fear, distrust or paranoia",
    "STIM-BLISSED": "Stim-Blissed: drugs or uncertain reality",
    "NEWGIRL": "Newgirl: Mentor demands",
    "CASUALTY": "Casualty: damaged parts or offered fixes",
    "OLDGEN": "Oldgen: history",
    "VATGROWN": "Vatgrown: Investors and demands",
    "ALPHA": "Alpha: opportunity for violence",
    "AM": "AM: risk of exposure",
    "BONDED": "Bonded: separation or conflicting aims",
    "THE PRINCE": "The Prince: fanbase demands",
    "CONSUME": "CONSUME: opportunity to take a bite",
    "JANUS-B": "JANUS: Harpy Core",
    "JANUS": "JANUS: Harpy Core",
    "DOCTORDOCTOR MK. II": "DoctorDoctor: time and Foundation demands",
    "WYVERN 0.4": "Wyvern: mysteries",
    "THE ENFORCER": "Enforcer: rebel NPC secrets",
    "CHANGELING": "CHANGELING: memories",
    "PROJECT ANKOU": "Ankou: civilian danger",
    "THE RED QUEEN": "Red Queen: AM demands",
}


def source_labels(state: GameState, grant: HandlerPlay) -> tuple[tuple[str, str], ...]:
    labels = []
    for ref in grant.targets:
        if ref.kind != "pilot":
            continue
        sheet = state.sheets.get(ref.entity)
        if sheet is None or sheet.character_id != ref.incarnation:
            continue
        for name in (sheet.girl, sheet.frame):
            if name in SOURCE_PROMPTS:
                labels.append((name, SOURCE_PROMPTS[name]))
    return tuple(dict.fromkeys(labels))


def _ordinary_scene_idle(c: Connection, game: "GameService") -> None:
    locks = t.m2["m2_locks"]
    if (
        game.pending_actions(c)
        or c.scalar(
            sa.select(locks.c.channel_id)
            .where(locks.c.campaign_id == game.store.campaign_id, locks.c.state != "released")
            .limit(1)
        )
        is not None
    ):
        raise WorkflowError(
            "Finish the pending Play and restore its chat before a new ordinary Handler Play."
        )


def request_handler_play(
    game: "GameService",
    c: Connection,
    source_action: str,
    source_choice: str,
    clause: str,
    chooser_actor: ActorRef,
    chooser_controller: int,
    victim_actor: ActorRef,
    event: str,
    *,
    state: GameState,
    final_original: bool = False,
) -> tuple[GameState, str]:
    action = game.action(c, source_action)
    choices = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id, choices.c.id == source_choice
            )
        )
        .mappings()
        .first()
    )
    if (
        action["data"].get("play") != "go_for_the_core"
        or row is None
        or row["action_id"] != source_action
        or row["actor_id"] != str(chooser_controller)
        or row["kind"] != "battle_counter"
        or clause not in ("go_for_the_core.high", "go_for_the_core.low")
    ):
        raise WorkflowError("A counter needs the actual printed Core choice and its human owner.")
    body = json.loads(row["body_json"])
    if body.get("actor") != chooser_actor.model_dump(mode="json") or body.get(
        "attacker"
    ) != victim_actor.model_dump(mode="json"):
        raise WorkflowError("The counter cannot choose another body or attacker.")
    bound = profiles(c, game.store.campaign_id)
    chooser_view = resolve(state, chooser_actor, bound, require_current_profile=False)
    if chooser_view.controller != chooser_controller:
        raise WorkflowError("Only the actual target's human controller owns this final counter.")
    if not final_original and chooser_view.rules not in ("handler", "director"):
        raise WorkflowError(
            "Only this actual Handler-rule body's own printed counter grants a Handler Play."
        )
    resolve(state, victim_actor, bound, require_current_profile=False)
    previous = next(
        (
            x
            for x in state.handler_plays
            if x.source_action == source_action and x.source_choice == source_choice
        ),
        None,
    )
    if previous:
        raise WorkflowError("This actual counter already has its one original Handler Play.")
    changed = GameState.model_validate_json(state.model_dump_json())
    identity = str(uuid4())
    changed.handler_plays.append(
        HandlerPlay(
            id=identity,
            source="battle_counter",
            source_event=event,
            source_action=source_action,
            source_choice=source_choice,
            clause=clause,
            chooser_actor=chooser_actor,
            chooser_controller=chooser_controller,
            targets=(victim_actor,),
            target_controllers={
                victim_actor.token: resolve(
                    state, victim_actor, bound, require_current_profile=False
                ).controller
            },
            scope=WorkScope(scene_id=action["scene_id"]),
            final_original=final_original,
        )
    )
    return changed, identity


def request_from_play(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    source_choice: str,
    clause: str,
    event: str,
    *,
    targets: tuple[ActorRef, ...],
) -> tuple[GameState, str]:
    chooser, appointment = MedicalService(game.store)._handler(c)
    choices = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == source_choice,
                choices.c.action_id == action["id"],
            )
        )
        .mappings()
        .first()
    )
    source_play = action["data"].get("play")
    adjudicator_ref, adjudicator_source = None, None
    if source_play == "all_out_assault":
        from girlframe.services.m3_battle import proved_judge

        adjudicator_ref, chooser, appointment = proved_judge(game, c, action)
        adjudicator_source = action["data"]["battle"].get("judge_source")
    if source_play == "doctor_support":
        meta = action["data"].get("doctor", {})
        chooser = meta.get("judge")
        adjudicator_ref = (
            ActorRef.model_validate(meta["judge_actor"]) if meta.get("judge_actor") else None
        )
        adjudicator_source = meta.get("judge_source")
        valid = (
            clause == "doctor_support.low"
            and row is not None
            and row["kind"] == "doctor_handler"
            and row["actor_id"] == str(chooser)
            and action["data"].get("result", {}).get("tier") == "low"
            and targets == (ActorRef.model_validate(meta["actor"]),)
        )
    elif source_play in ("am_scrutinized", "am_just_code"):
        meta = action["data"].get("am_scrutinized", {})
        code_source = True
        if source_play == "am_just_code":
            from girlframe.services.m3_am_code import prove_code_discovery

            discovered = prove_code_discovery(game, c, state, action)
            code_source = (
                bool(discovered.code_origin)
                and discovered.handler_controller == chooser
                and discovered.caster == int(action["actor_id"])
                and targets == (discovered.actor,)
                and ActorRef.model_validate(meta["actor"]) == discovered.actor
            )
        valid = (
            code_source
            and clause == "am_scrutinized.refuge"
            and row is not None
            and row["kind"] == "am_handler"
            and row["actor_id"] == str(chooser)
            and meta.get("handler_controller") == chooser
            and action["data"].get("result", {}).get("tier") in ("mid", "high")
            and targets == (ActorRef.model_validate(meta["actor"]),)
        )
    elif source_play == "flirt":
        valid = (
            clause == "flirt.high.handler"
            and row is not None
            and row["kind"] == "handler_brief"
            and row["actor_id"] == str(chooser)
            and action["data"].get("result", {}).get("extra") == "handler"
            and action["data"].get("result", {}).get("tier") == "high"
        )
    else:
        valid = (
            source_play == "all_out_assault"
            and clause in ("all_out_assault.high", "all_out_assault.low")
            and row is not None
            and row["kind"] in ("battle_handler", "battle_low_damage")
            and action["data"].get("result", {}).get("tier") == clause.rsplit(".", 1)[1]
        )
    if not valid or not action["data"].get("receipt") or not targets:
        raise WorkflowError(
            "A required Handler Play needs its actual printed source choice and known receipt."
        )
    assert row is not None
    if source_play == "all_out_assault":
        if len(targets) != 1 or json.loads(row["body_json"]).get("actor") != targets[0].model_dump(
            mode="json"
        ):
            raise WorkflowError(
                "The required Handler Play must affect the actual original All-Out actor."
            )
    if source_play == "flirt":
        if action["data"].get("clone_flirt"):
            meta = action["data"]["clone_flirt"]
            expected = {
                ActorRef.model_validate(meta["actor"]),
                ActorRef.model_validate(meta["target"]),
            }
        else:
            identities = action["data"].get("character_ids") or game.legacy_action_bindings(
                c, action
            )
            owners = (int(action["actor_id"]), int(action["data"]["prepared"]["target"]))
            expected = {
                ActorRef(kind="pilot", entity=str(uid), incarnation=identities.get(str(uid)))
                for uid in owners
            }
        if set(targets) != expected:
            raise WorkflowError(
                "A Flirt Handler Play is scoped to the actual two original participants."
            )
    source_human = (
        action["data"].get("doctor", {}).get("judge")
        if source_play == "doctor_support"
        else action["data"].get("battle", {}).get("handler")
        if source_play == "all_out_assault"
        else action["data"].get("handler")
    )
    if chooser != source_human:
        raise WorkflowError("Recover the actual source's original GM appointment.")
    if any(
        x.source_action == action["id"] and x.source_choice == source_choice
        for x in state.handler_plays
    ):
        raise WorkflowError("This actual source choice already has its owned Handler Play.")
    bound = profiles(c, game.store.campaign_id)
    target_controllers = {}
    nonbody_only = False
    for target in targets:
        try:
            target_controllers[target.token] = resolve(
                state, target, bound, require_current_profile=False
            ).controller
        except ValueError:
            from girlframe.services.m3_battle import proved_ended_original

            if (
                source_play != "all_out_assault"
                or clause != "all_out_assault.low"
                or len(targets) != 1
                or not proved_ended_original(game, c, state, action, target)
            ):
                raise
            target_controllers[target.token] = int(target.entity)
            nonbody_only = True
    changed = GameState.model_validate_json(state.model_dump_json())
    identity = str(uuid4())
    changed.handler_plays.append(
        HandlerPlay(
            id=identity,
            source="required",
            source_event=event,
            source_action=action["id"],
            source_choice=source_choice,
            clause=clause,
            chooser_actor=None,
            chooser_controller=chooser,
            appointment=appointment,
            adjudicator_ref=adjudicator_ref,
            adjudicator_source=adjudicator_source,
            targets=targets,
            target_controllers=target_controllers,
            nonbody_only=nonbody_only,
            scope=WorkScope(scene_id=action["scene_id"]),
        )
    )
    c.execute(
        choices.update()
        .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == source_choice)
        .values(
            body_json=json.dumps(json.loads(row["body_json"]) | dict(handler_grant=identity)),
            revision=row["revision"] + 1,
        )
    )
    return changed, identity


def request_forced_handler_play(
    game: "GameService",
    c: Connection,
    state: GameState,
    *,
    source_action: str,
    source_choice: str,
    clause: str,
    chooser_controller: int,
    victim_actor: ActorRef,
    event: str,
    action: dict[str, Any] | None = None,
) -> tuple[GameState, str]:
    from girlframe.services.m3_battle import proved_judge

    original_action = (
        action
        if action is not None and action["id"] == source_action
        else game.action(c, source_action)
    )
    if proved_judge(game, c, original_action)[1] != chooser_controller:
        raise WorkflowError("Only the actual source's frozen human judge owns this required Play.")
    return request_from_play(
        game,
        c,
        state,
        original_action,
        source_choice,
        clause,
        event,
        targets=(victim_actor,),
    )


def validate_damage_source(
    c: Connection,
    game: "GameService",
    state: GameState,
    identity: str,
    target: ActorRef,
    actor: ActorRef | None,
    chooser_controller: int | None,
    event: str,
) -> None:
    _, original = _source(c, game, identity)
    _authority(c, game, state, original)
    staged = rules.record(state, identity)
    if (
        original.state != "pending"
        or staged.state != "awaiting_effect"
        or staged.effect is None
        or staged.effect.kind != "damage"
        or staged.effect_event != event
        or staged.effect.target != target
        or original.chooser_actor != actor
        or original.chooser_controller != chooser_controller
        or target not in original.targets
    ):
        raise WorkflowError("Use the actual source-owned original damage effect and chooser.")


def _source(c: Connection, game: "GameService", identity: str) -> tuple[GameState, HandlerPlay]:
    state = load_state(c, game.store.campaign_id)
    try:
        grant = rules.record(state, identity)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    history = t.m2["m2_state_history"]
    body = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == grant.source_event,
        )
    )
    original = GameState.model_validate_json(body) if body else None
    first = (
        next((x for x in original.handler_plays if x.id == identity), None) if original else None
    )
    fields = (
        "id",
        "source",
        "source_event",
        "source_action",
        "source_choice",
        "clause",
        "chooser_actor",
        "chooser_controller",
        "appointment",
        "adjudicator_ref",
        "adjudicator_source",
        "targets",
        "target_controllers",
        "scope",
        "final_original",
        "nonbody_only",
    )
    if first is None or any(getattr(first, k) != getattr(grant, k) for k in fields):
        raise WorkflowError(
            "SOURCE_HANDLER_PLAY_MISSING: recover this actual owned grant's immutable event."
        )
    if grant.clause.startswith("tracker:"):
        from girlframe.services.m3_tracker_implants import prove_tracker_play

        prove_tracker_play(game, c, state, grant)
    elif grant.clause.startswith("contaminant-zone:"):
        from girlframe.services.m3_contaminant_zone import prove_warp

        prove_warp(game, c, state, grant)
    if grant.clause == "ship_base.low":
        from girlframe.services.m3_ship_base import prove_low_grant

        prove_low_grant(game, c, state, grant)
    if grant.source == "battle_counter":
        answer = c.scalar(
            sa.select(t.m2["m2_responses"].c.answer_json).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == grant.source_choice,
                t.m2["m2_responses"].c.event_id == grant.source_event,
                t.m2["m2_responses"].c.actor_id == str(grant.chooser_controller),
            )
        )
        option = (
            "target_dies_with_handler_play" if grant.final_original else "make_play_against_actor"
        )
        if answer is None or option not in json.loads(answer).get("options", []):
            raise WorkflowError("Recover the actual original target's printed counter choice.")
        if not grant.final_original:
            assert original is not None
            try:
                chooser = (
                    resolve(
                        original,
                        grant.chooser_actor,
                        profiles(c, game.store.campaign_id),
                        require_current_profile=False,
                    )
                    if grant.chooser_actor is not None
                    else None
                )
            except ValueError:
                chooser = None
            if (
                chooser is None
                or chooser.rules not in ("handler", "director")
                or (chooser.controller != grant.chooser_controller)
            ):
                raise WorkflowError(
                    "The actual original Handler-rule body owns this narrow printed counter."
                )
    if grant.effect_event is not None:
        applied_raw = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.event_id == grant.effect_event,
            )
        )
        applied_state = GameState.model_validate_json(applied_raw) if applied_raw else None
        applied = (
            next((x for x in applied_state.handler_plays if x.id == grant.id), None)
            if applied_state
            else None
        )
        actor = c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == grant.effect_event,
                t.events.c.kind == "m3.handler_play_applied",
            )
        )
        if (
            applied is None
            or actor != str(grant.chooser_controller)
            or any(
                getattr(applied, k) != getattr(grant, k)
                for k in ("selected", "effect", "effect_event", "followups")
            )
        ):
            raise WorkflowError(
                "Recover the actual original chooser's committed Handler Play effect."
            )
    return state, grant


def _authority(c: Connection, game: "GameService", state: GameState, grant: HandlerPlay) -> None:
    if not HandlerService(game.store)._member(c, grant.chooser_controller):
        raise WorkflowError("The original decision owner must remain a campaign member.")
    if grant.clause.startswith("tracker:"):
        from girlframe.services.m3_tracker_implants import prove_tracker_play

        prove_tracker_play(game, c, state, grant)
    elif grant.clause.startswith("contaminant-zone:"):
        from girlframe.services.m3_contaminant_zone import prove_warp

        prove_warp(game, c, state, grant)
    if grant.clause == "ship_base.low":
        from girlframe.services.m3_ship_base import prove_low_grant

        prove_low_grant(game, c, state, grant)
    if grant.source in ("ordinary", "required"):
        if grant.source == "required" and grant.clause == "doctor_support.low":
            from girlframe.services.m3_battle import _scene_judge
            from girlframe.services.m3_enforcement_initiative import _cast

            if grant.source_action is None:
                raise WorkflowError("Recover the original Support source action")
            source_action = game.action(c, grant.source_action)
            meta = source_action["data"].get("doctor", {})
            judge, human, source = _scene_judge(
                game, c, state, _cast(game, c, state, int(source_action["channel_id"]))
            )
            if (
                (judge, human, source)
                != (grant.adjudicator_ref, grant.chooser_controller, grant.adjudicator_source)
                or source_action["data"].get("play") != "doctor_support"
                or source_action["data"].get("result", {}).get("tier") != "low"
                or meta.get("appointment") != grant.appointment
            ):
                raise WorkflowError("Recover the actual original Support source judge")
            return
        if grant.source == "required" and grant.clause.startswith("all_out_assault."):
            from girlframe.services.m3_battle import proved_judge

            if grant.source_action is None:
                raise WorkflowError("Recover the actual source battle for this required Play.")
            source_action = game.action(c, grant.source_action)
            ref, human, appointment = proved_judge(game, c, source_action)
            if (ref, human, appointment) != (
                grant.adjudicator_ref,
                grant.chooser_controller,
                grant.appointment,
            ) or source_action["data"]["battle"].get("judge_source") != grant.adjudicator_source:
                raise WorkflowError("Recover the exact original battle judge episode.")
            if grant.nonbody_only:
                from girlframe.services.m3_battle import proved_ended_original

                if not proved_ended_original(game, c, state, source_action, grant.targets[0]):
                    raise WorkflowError(
                        "Recover the actual original-ended source before its procedure."
                    )
            return
        if MedicalService(game.store)._handler(c) != (grant.chooser_controller, grant.appointment):
            raise WorkflowError(
                "The original GM appointment changed; this saved move cannot transfer."
            )
        if grant.source == "ordinary" and grant.chooser_actor != active_handler(state):
            raise WorkflowError(
                "The original Handler body context changed; withdraw this untouched move "
                "and start a fresh one."
            )
        return
    assert grant.chooser_actor is not None
    try:
        actor = resolve(
            state,
            grant.chooser_actor,
            profiles(c, game.store.campaign_id),
            require_current_profile=False,
        )
    except ValueError:
        if not grant.final_original:
            raise WorkflowError("The original counter body is unavailable.") from None
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.event_id == grant.source_event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else GameState()
        proof = any(
            x.actor == grant.chooser_actor
            and x.source_event == grant.source_event
            and x.ending in ("death", "execution")
            for x in original.career_archives
        )
        if grant.chooser_actor.kind == "handler":
            try:
                actual_body = body_original(original, grant.chooser_actor)
            except ValueError:
                proof = False
            else:
                proof = any(
                    x.body == actual_body and x.source_event == grant.source_event
                    for x in original.handler_archives
                )
        if original.world:
            if grant.chooser_actor.kind == "npc":
                proof = any(
                    x.id == grant.chooser_actor.entity
                    and not x.alive
                    and x.controller == grant.chooser_controller
                    for x in original.world.npcs
                )
            elif grant.chooser_actor.kind == "external_pilot":
                proof = any(
                    x.id == grant.chooser_actor.entity
                    and not x.alive
                    and x.controller == grant.chooser_controller
                    for x in original.world.pilots
                )
            elif grant.chooser_actor.kind == "gorgon":
                proof = any(
                    x.id == grant.chooser_actor.entity and not x.alive
                    for x in original.world.gorgons
                )
            proof = proof or any(
                x.id == grant.chooser_actor.entity
                and not x.alive
                and x.controller == grant.chooser_controller
                for x in original.harpy_states
            )
        if not proof:
            raise WorkflowError(
                "Recover the exact dying original's last-act source; no replacement may act."
            ) from None
    else:
        if actor.controller != grant.chooser_controller:
            raise WorkflowError("The original counter's human controller changed.")


def validate_role_case(
    c: Connection, game: "GameService", state: GameState, case: "RolePunishment"
) -> None:
    from girlframe.services.m3_intracadre_marriage import original_offender

    offender = original_offender(game, c, state, case.id, case.source_event, case.subject)
    _, grant = _source(c, game, case.source_work or "")
    _authority(c, game, state, grant)
    if (
        (
            grant.state != "awaiting_effect"
            and not (
                grant.state == "complete"
                and case.completion_event is not None
                and grant.completed_event == case.completion_event
            )
        )
        or case.id not in grant.followups
        or grant.effect is None
        or grant.effect.kind != "punish"
        or case.chooser != grant.chooser_actor
        or case.executor != grant.effect.executor
        or case.chooser_controller != grant.chooser_controller
        or offender != grant.effect.target
        or offender not in grant.targets
    ):
        raise WorkflowError("This exact Handler Play cannot authorize another Punishment or body.")


def role_scope(c: Connection, game: "GameService", case: "RolePunishment") -> WorkScope:
    _, grant = _source(c, game, case.source_work or "")
    return grant.scope


def _continuation(c: Connection, game: "GameService", event: str) -> tuple[str, str, int]:
    source = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.command_key).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if source is None:
        raise WorkflowError("Recover the actual completed effect's audit source.")
    last = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == source.command_key,
        )
    )
    return str(source.actor_id), str(source.command_key), int(last or 0) + 1


def _complete(
    game: "GameService", c: Connection, state: GameState, identity: str, event: str
) -> GameState:
    updated = rules.complete(state, identity, event)
    grant = rules.record(updated, identity)
    if grant.clause == "ship_base.low":
        from girlframe.services.m3_ship_base import complete_low

        complete_low(game, c, updated, grant, event)
    return updated


def complete_role_case(
    c: Connection, game: "GameService", case: "RolePunishment", event: str
) -> None:
    state, grant = _source(c, game, case.source_work or "")
    if not case.completion_event:
        raise WorkflowError("Complete the actual punishment and all source followups first.")
    if grant.state == "complete":
        return
    updated = _complete(game, c, state, grant.id, event)
    actor, key, index = _continuation(c, game, event)
    completed = game.event(
        c,
        actor,
        key,
        "m3.handler_play_completed",
        updated,
        event_index=index,
        grant_id=grant.id,
        role_case=case.id,
        source_event=event,
    )
    # The actual executor's service supplies its real viewer to source continuations.
    # Battle completion validates the grant; no fictional controller is impersonated.
    if grant.source in ("battle_counter", "required"):
        finish_callback(game, c, rules.record(updated, grant.id), completed, None, key)


def complete_damage(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    state, grant = _source(c, game, identity)
    if grant.effect is None or grant.effect.kind != "damage":
        raise WorkflowError("This source is not an actual owned Handler damage effect.")
    if grant.state == "complete":
        return
    work = t.m3["m3_required_work"]
    latest = {
        row["id"]: dict(row)
        for row in c.execute(
            sa.select(work)
            .where(work.c.campaign_id == game.store.campaign_id)
            .order_by(work.c.revision)
        ).mappings()
    }
    chain = set(grant.followups)
    while True:
        children = {
            row["id"]
            for row in latest.values()
            if json.loads(row["body_json"]).get("source_work") in chain
            and json.loads(row["body_json"]).get("immediate")
        }
        if children <= chain:
            break
        chain |= children
    if not grant.followups or any(
        identity not in latest or latest[identity]["state"] != "resolved" for identity in chain
    ):
        raise WorkflowError(
            "Finish the actual source damage consequences and owned followups first."
        )
    state = _complete(game, c, state, grant.id, event)
    actor, command, index = _continuation(c, game, event)
    saved = game.event(
        c,
        actor,
        command,
        "m3.handler_damage_play_completed",
        state,
        event_index=index,
        source_event=event,
        grant_id=grant.id,
    )
    finish_callback(game, c, rules.record(state, grant.id), saved, viewer, key)


def _off_duty(c: Connection, game: "GameService", grant: HandlerPlay, identity: str) -> "Period":
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService

    periods = OffDutyService(MissionService(game.store))
    period = periods._get(c, identity)
    if period.phase == "complete":
        raise WorkflowError("Choose an actual current Off-Duty period, not a past phase.")
    for ref in grant.targets:
        if (
            ref.kind != "pilot"
            or period.character_ids.get(ref.entity) != ref.incarnation
            or ref.entity in period.ended_characters
        ):
            raise WorkflowError(
                "This Off-Duty period does not include the actual affected original Girls."
            )
    if grant.source != "ordinary" and game.pending_actions(c):
        raise WorkflowError(
            "The held source Play must finish before Cadre phase changes; choose "
            "another eligible Handler Play."
        )
    if grant.source == "battle_counter":
        scene = period.handler_scene
        if (
            scene is None
            or grant.chooser_controller not in scene.participants
            or any(int(x.entity) not in scene.participants for x in grant.targets)
        ):
            raise WorkflowError(
                "This counter needs an actual owned attacker-involving Handler Off-Duty scene."
            )
    return period


def synchronize_off_duty(c: Connection, game: "GameService", period: "Period", event: str) -> None:
    if period.phase != "complete":
        return
    state = load_state(c, game.store.campaign_id)
    completed = []
    for grant in state.handler_plays:
        if (
            grant.state == "awaiting_effect"
            and grant.effect
            and grant.effect.kind == "off_duty"
            and grant.effect.off_duty == period.id
        ):
            if (
                period.handler_scene is None
                or set(period.handler_scene.participants)
                != set(period.handler_scene.acknowledgements)
                or period.status_review is None
            ):
                raise WorkflowError(
                    "The actual Handler scene and performance review must finish first."
                )
            state = _complete(game, c, state, grant.id, event)
            completed.append(grant.id)
    if completed:
        actor, key, index = _continuation(c, game, event)
        saved = game.event(
            c,
            actor,
            key,
            "m3.handler_off_duty_plays_completed",
            state,
            event_index=index,
            source_event=event,
            grants=completed,
        )
        for identity in completed:
            finish_callback(game, c, rules.record(state, identity), saved, None, key)


def finish_callback(
    game: "GameService",
    c: Connection,
    grant: HandlerPlay,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    if not (
        grant.state == "complete"
        and grant.completed_event
        or grant.source == "battle_counter"
        and grant.state == "declined"
        and grant.declined_event
    ):
        raise WorkflowError("The Handler Play's actual effect and followups must finish first.")
    if grant.clause == "ship_base.low":
        from girlframe.services.m3_ship_base import prove_low_grant

        prove_low_grant(game, c, load_state(c, game.store.campaign_id), grant)
        return
    if grant.source == "required":
        assert grant.source_action is not None and grant.source_choice is not None
        action = game.action(c, grant.source_action)
        if action["data"].get("am_scrutinized"):
            from girlframe.services.m3_am_scrutinized import complete_handler

            complete_handler(game, c, grant, event)
            return
        if action["data"].get("play") not in ("flirt", "doctor_support"):
            from girlframe.services.m3_battle import complete_handler_play

            complete_handler_play(game, c, grant, event, viewer, key)
            return
        choices = t.m2["m2_choices"]
        row = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.id == grant.source_choice,
                    choices.c.action_id == grant.source_action,
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["kind"]
            != ("doctor_handler" if action["data"].get("doctor") else "handler_brief")
            or row["actor_id"] != str(grant.chooser_controller)
            or json.loads(row["body_json"]).get("handler_grant") != grant.id
        ):
            raise WorkflowError("Recover the actual source-owned required Handler choice.")
        if row["state"] not in ("pending", "submitted"):
            return
        c.execute(
            choices.update()
            .where(
                choices.c.campaign_id == game.store.campaign_id, choices.c.id == grant.source_choice
            )
            .values(
                state="completed_by_work",
                revision=row["revision"] + 1,
                body_json=json.dumps(
                    json.loads(row["body_json"]) | dict(handler_play_event=grant.completed_event)
                ),
            )
        )
        action["data"]["result"]["handler_play"] = grant.effect.kind if grant.effect else None
        action["data"]["result"]["handler_text"] = grant.effect.account if grant.effect else ""
        if not game.pending(c, action["id"]):
            from girlframe.services.m2_choices import ChoiceEngine

            if action["data"].get("clone_flirt"):
                from girlframe.services.m3_actor_plays import ActorPlayService

                ActorPlayService(game).finish(c, load_state(c, game.store.campaign_id), action)
            else:
                ChoiceEngine(game).finish(c, load_state(c, game.store.campaign_id), action)
        game.save_action(c, action)
        if action["state"] == "complete" and action["data"].get("battle_counter_source"):
            from girlframe.services.m3_battle import complete_counter_play

            complete_counter_play(game, c, action, event, viewer, key)
    elif grant.source == "battle_counter":
        from girlframe.services.m3_battle import complete_handler_play

        complete_handler_play(game, c, grant, event, viewer, key)


class HandlerPlayService:
    def __init__(self, store: OnboardingStore):
        from girlframe.services.m2_game import GameService

        self.store, self.game = store, GameService(store)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                kind="handler_play",
                label="Choose your source-owned Handler Play",
                state=x.state,
                can_act=x.state == "pending",
            )
            for x in state.handler_plays
            if x.chooser_controller == viewer.user_id
            and x.state not in ("complete", "withdrawn", "declined")
        ]

    def _notices(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                kind="handler_notice",
                label="Read actual Handler Play: " + str(x.selected),
                state=x.state,
            )
            for x in reversed(state.handler_plays)
            if x.effect_event
            and (
                (x.selected == "tracker_voyeur" and viewer.user_id == x.chooser_controller)
                or (
                    x.selected != "tracker_voyeur"
                    and viewer.user_id in x.target_controllers.values()
                )
            )
        ][:25]

    def notice(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            _, grant = _source(c, self.game, identity)
            if (
                viewer.user_id not in grant.target_controllers.values()
                and viewer.user_id != grant.chooser_controller
            ):
                raise WorkflowError(
                    "This actual source information belongs to its original participants."
                )
            if grant.effect is None or grant.effect_event is None:
                raise WorkflowError("The owner has not committed this actual Handler Play yet.")
            effect = grant.effect
            if grant.selected == "tracker_voyeur" and viewer.user_id != grant.chooser_controller:
                raise WorkflowError("This observed knowledge belongs only to its original Handler")
            return dict(
                id=identity,
                play=grant.selected,
                state=grant.state,
                account=effect.account,
                detail=effect.detail,
                stakes=effect.stakes,
                tag=effect.tag,
                employee=dict(name=effect.npc.name) if effect.npc else None,
            )

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)

    def options(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            HandlerService(self.store).authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            from girlframe.services.m3_contaminant_zone import warp_options

            return dict(
                game_revision=state.revision,
                plays=BASIC,
                targets=[
                    dict(
                        ref=ActorRef(
                            kind="pilot", entity=uid, incarnation=s.character_id
                        ).model_dump(mode="json"),
                        label=s.callsign,
                    )
                    for uid, s in state.sheets.items()
                    if s.character_id
                ],
                tasks=self._tasks(c, viewer),
                warp_zones=warp_options(self.game, c, state, active_handler(state)),
            )

    def start_warp(self, viewer: GuildViewer, key: str, expected: int, zone: str) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            HandlerService(self.store).authorize(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_contaminant_zone import start_warp

            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected:
                raise WorkflowError("Reopen the actual active quarantined zone")
            event = str(uuid4())
            identity = start_warp(self.game, c, state, viewer, zone, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_play_started",
                state,
                event_id=event,
                grant_id=identity,
            )
            return dict(id=identity, game_revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.handler_play_started",
            dict(expected=expected, zone=zone),
            operation,
            auto_audit=False,
            authorize=access,
        )

    def start(
        self, viewer: GuildViewer, key: str, expected: int, targets: tuple[ActorRef, ...]
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            HandlerService(self.store).authorize(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected:
                raise WorkflowError("The canonical state changed; reopen Handler Plays.")
            bound = profiles(c, self.store.campaign_id)
            for actor in targets:
                resolve(state, actor, bound, require_current_profile=False)
            owner, appointment = MedicalService(self.store)._handler(c)
            identity, event = str(uuid4()), str(uuid4())
            state.handler_plays.append(
                HandlerPlay(
                    id=identity,
                    source="ordinary",
                    source_event=event,
                    clause="basic_handler_play",
                    chooser_actor=active_handler(state),
                    chooser_controller=owner,
                    appointment=appointment,
                    targets=targets,
                    target_controllers={
                        target.token: resolve(
                            state, target, bound, require_current_profile=False
                        ).controller
                        for target in targets
                    },
                    scope=WorkScope(campaign_context=True),
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_play_started",
                state,
                event_id=event,
                grant_id=identity,
            )
            return dict(id=identity, game_revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.handler_play_started",
            dict(expected=expected, targets=[x.model_dump(mode="json") for x in targets]),
            operation,
            auto_audit=False,
            authorize=access,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state, grant = _source(c, self.game, identity)
            if viewer.user_id != grant.chooser_controller:
                raise WorkflowError(
                    "Only this actual Handler Play's human chooser may open its private details."
                )
            stale = None
            try:
                _authority(c, self.game, state, grant)
            except WorkflowError as error:
                stale = str(error)
            bound = profiles(c, self.store.campaign_id)
            targets: list[dict[str, Any]] = []
            for ref in grant.targets:
                try:
                    actor = resolve(state, ref, bound, require_current_profile=False)
                except ValueError:
                    if ref.kind == "handler":
                        original = body_original(state, ref)
                        persona = (
                            json.loads(original.persona_json) if original.persona_json else None
                        )
                        label = persona["draft"]["name"] if persona else "Original Handler"
                        targets.append(
                            dict(
                                ref=ref.model_dump(mode="json"),
                                token=ref.token,
                                label=label + " (original character)",
                                assets=[],
                                rules="archived",
                            )
                        )
                        stale = stale or "The original affected Handler body ended."
                        continue
                    if ref.kind != "pilot":
                        actor = resolve(
                            state, ref, bound, require_current_profile=False, require_alive=False
                        )
                    else:
                        archived = original_sheet(state, ref)
                        targets.append(
                            dict(
                                ref=ref.model_dump(mode="json"),
                                token=ref.token,
                                label=archived.callsign + " (original character)",
                                assets=[],
                                rules="archived",
                            )
                        )
                        if not grant.nonbody_only:
                            stale = (
                                stale
                                or "The original affected character ended; no replacement "
                                "can inherit this effect."
                            )
                        continue
                targets.append(
                    dict(
                        ref=ref.model_dump(mode="json"),
                        token=ref.token,
                        label=actor.label,
                        assets=[
                            dict(id=x.id, name=x.name)
                            for x in actor.assets
                            if not x.damaged
                            and (
                                grant.source != "battle_counter"
                                or actor.controller == viewer.user_id
                                or not x.concealed
                            )
                        ],
                        rules=actor.rules,
                    )
                )
            executors = []
            executor_refs = list(owned_refs(state, viewer.user_id, bound))
            executor_refs.extend(
                ActorRef(kind="pilot", entity=uid, incarnation=x.character_id)
                for uid, x in state.sheets.items()
                if x.character_id
            )
            handler_body = active_handler(state)
            if handler_body is not None:
                executor_refs.append(handler_body)
            if state.world:
                executor_refs.extend(
                    ActorRef(kind="npc", entity=x.id)
                    for x in state.world.npcs
                    if x.revealed and x.alive
                )
            for ref in dict.fromkeys(executor_refs):
                if ref in grant.targets:
                    continue
                try:
                    actor = resolve(state, ref, bound, require_current_profile=False)
                except ValueError:
                    continue
                executors.append(
                    dict(ref=ref.model_dump(mode="json"), token=ref.token, label=actor.label)
                )
            special_plays = None
            observed = None
            zone = None
            if grant.clause.startswith("tracker:"):
                from girlframe.engine import m3_tracker_implants as trackers
                from girlframe.services.m3_tracker_implants import prove_moment, prove_tracker_play

                source = prove_tracker_play(self.game, c, state, grant)
                special_plays = tuple(x for x in trackers.PLAYS if x[0] == source.play)
                if source.moment:
                    observed = prove_moment(self.game, c, state, source.moment).account
            elif grant.clause.startswith("contaminant-zone:"):
                from girlframe.engine.m3_handler_play_state import EXTRA
                from girlframe.services.m3_contaminant_zone import prove_warp

                zone = prove_warp(self.game, c, state, grant).id
                special_plays = tuple(x for x in EXTRA if x[0] == "contaminant_warp")
            return dict(
                id=identity,
                game_revision=state.revision,
                grant=grant.model_dump(mode="json"),
                stale=stale,
                targets=targets,
                observed_moment=observed,
                zone=zone,
                plays=special_plays
                or tuple(
                    x
                    for x in BASIC
                    if not grant.nonbody_only
                    or x[0] in ("brief", "escalate", "support", "expectation")
                ),
                executors=executors,
                locations=tuple((x.id, x.name) for x in state.world.locations)
                if state.world
                else (),
                location_records=[dict(id=x.id, cell=x.cell) for x in state.world.locations]
                if state.world
                else [],
                source_labels=source_labels(state, grant),
                off_duty=c.scalar(
                    sa.select(t.m3["m3_off_duty"].c.id).where(
                        t.m3["m3_off_duty"].c.campaign_id == self.store.campaign_id,
                        t.m3["m3_off_duty"].c.phase != "complete",
                    )
                ),
            )

    def decline(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state, grant = _source(c, self.game, identity)
            _authority(c, self.game, state, grant)
            if (
                state.revision != expected
                or grant.source != "battle_counter"
                or grant.state != "pending"
                or grant.chooser_controller != viewer.user_id
            ):
                raise WorkflowError(
                    "Only the actual owner may decline their untouched optional source counter."
                )
            event = str(uuid4())
            rules.replace(
                state, grant.model_copy(update=dict(state="declined", declined_event=event))
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_counter_declined",
                state,
                event_id=event,
                grant_id=identity,
            )
            finish_callback(self.game, c, rules.record(state, identity), event, viewer, key)
            return dict(id=identity, state="declined")

        return self.store._write(
            viewer,
            key,
            "m3.handler_counter_declined",
            dict(id=identity, expected=expected),
            operation,
            auto_audit=False,
            authorize=access,
        )

    def withdraw(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            HandlerService(self.store).authorize(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state, grant = _source(c, self.game, identity)
            if (
                state.revision != expected
                or grant.source != "ordinary"
                or grant.state != "pending"
                or grant.chooser_controller != viewer.user_id
                or MedicalService(self.store)._handler(c)
                != (grant.chooser_controller, grant.appointment)
            ):
                raise WorkflowError(
                    "Only the original GM may withdraw their untouched ordinary move."
                )
            event = str(uuid4())
            rules.replace(
                state, grant.model_copy(update=dict(state="withdrawn", withdrawn_event=event))
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_play_withdrawn",
                state,
                event_id=event,
                grant_id=identity,
            )
            return dict(id=identity, state="withdrawn")

        return self.store._write(
            viewer,
            key,
            "m3.handler_play_withdrawn",
            dict(id=identity, expected=expected),
            operation,
            auto_audit=False,
            authorize=access,
        )

    def submit(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        play: Play,
        effect: Effect,
    ) -> dict[str, Any]:
        effect = Effect.model_validate_json(effect.model_dump_json())

        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            self.game.unpaused(c)
            state, grant = _source(c, self.game, identity)
            if grant.chooser_controller != viewer.user_id:
                raise WorkflowError("Only the original human chooser may make this Handler Play.")
            _authority(c, self.game, state, grant)

        def operation(c: Connection) -> dict[str, Any]:
            state, grant = _source(c, self.game, identity)
            if grant.source == "ordinary":
                _ordinary_scene_idle(c, self.game)
            if state.revision != expected:
                raise WorkflowError("The scene changed; reopen the saved Handler Play.")
            if effect.kind in ("expectation", "tracker_intercept"):
                from girlframe.services.m3_vatgrown import (
                    require_attention as require_doll_attention,
                )

                for target in (effect.target,) if effect.target else grant.targets:
                    for cast in state.scene_casts:
                        if (
                            cast.open
                            and any(x.actor == target for x in cast.roles)
                            and any(x.actor == grant.chooser_actor for x in cast.roles)
                        ):
                            require_doll_attention(
                                self.game,
                                c,
                                state,
                                target,
                                cast.id,
                                "expectation" if effect.kind == "expectation" else "intercept",
                            )
            if effect.target is not None:
                resolve(
                    state,
                    effect.target,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
            if effect.threat is not None:
                resolve(
                    state,
                    effect.threat,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
            if (
                effect.kind != "contaminant_warp"
                and effect.source_label is not None
                and effect.source_label not in dict(source_labels(state, grant))
            ):
                raise WorkflowError(
                    "This optional source prompt does not belong to the actual affected Cadre."
                )
            event = str(uuid4())
            state = rules.select(state, identity, play, effect, event)
            if effect.kind in ("tracker_intercept", "tracker_voyeur"):
                from girlframe.services.m3_tracker_implants import apply_play

                state = apply_play(self.game, c, state, grant, effect)
                state = _complete(self.game, c, state, identity, event)
            elif effect.kind == "contaminant_warp":
                from girlframe.services.m3_contaminant_zone import apply_warp, prove_warp

                zone_source = prove_warp(self.game, c, state, grant)
                if (
                    grant.chooser_actor is None
                    or grant.appointment is None
                    or effect.cell is None
                    or effect.zone != zone_source.id
                ):
                    raise WorkflowError("Use the exact source-owned zone and original Handler")
                state = apply_warp(
                    self.game,
                    c,
                    state,
                    handler=grant.chooser_actor,
                    appointment=grant.appointment,
                    zone=zone_source.id,
                    cell=effect.cell,
                    label=effect.source_label or "",
                    description=effect.detail,
                    event=event,
                    grant=identity,
                    scene=grant.scope.scene_id,
                )
                state = _complete(self.game, c, state, identity, event)
            elif effect.kind == "off_duty":
                assert effect.off_duty is not None
                _off_duty(c, self.game, grant, effect.off_duty)
            elif effect.kind == "punish":
                from girlframe.services.m3_role_punishments import open_case

                if effect.target is None or effect.executor is None:
                    raise WorkflowError(
                        "Choose the actual affected original and living physical inflictor."
                    )
                executor = resolve(
                    state,
                    effect.executor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                state, case_id = open_case(
                    state,
                    profiles(c, self.store.campaign_id),
                    actor=effect.executor,
                    target=effect.target,
                    chooser=grant.chooser_actor,
                    source_kind="handler_play",
                    action=grant.source_action,
                    source_event=event,
                    identity="handler-punishment:" + grant.id,
                    source_work=grant.id,
                    chooser_controller=grant.chooser_controller,
                    executor_controller=executor.controller,
                )
                rules.replace(
                    state,
                    rules.record(state, identity).model_copy(update=dict(followups=(case_id,))),
                )
            elif effect.kind == "damage":
                from girlframe.services.m3_battle import damage_actor

                assert effect.target is not None
                state, required = damage_actor(
                    self.game,
                    c,
                    state,
                    target=effect.target,
                    asset_id=effect.asset,
                    source_action=(
                        None if grant.clause == "ship_base.low" else grant.source_action
                    ),
                    source_work=grant.id,
                    event=event,
                    actor=grant.chooser_actor,
                    opponent=effect.opponent,
                    chooser_controller=grant.chooser_controller,
                    occurrence="handler-play:" + grant.id,
                )
                rules.replace(
                    state, rules.record(state, identity).model_copy(update=dict(followups=required))
                )
                if not required:
                    state = _complete(self.game, c, state, identity, event)
            else:
                state = rules.direct(state, identity, event)
                state = _complete(self.game, c, state, identity, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_play_applied",
                state,
                event_id=event,
                grant_id=identity,
                play=play,
            )
            if effect.kind == "punish":
                from girlframe.services.m3_role_punishments import synchronize

                synchronize(self.game, c, None, event)
            elif effect.kind == "damage":
                from girlframe.services.m3_battle import synchronize_damage

                synchronize_damage(self.game, c, event)
            actual = rules.record(state, identity)
            if actual.state == "complete":
                finish_callback(self.game, c, actual, event, viewer, key)
            return dict(id=identity, state=actual.state, game_revision=state.revision)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_play_applied",
                dict(
                    id=identity, expected=expected, play=play, effect=effect.model_dump(mode="json")
                ),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def verified_tag_grants(
    c: Connection,
    game: "GameService",
    previous: GameState,
    staged: GameState,
    *,
    actor: int | None,
    event: str,
    kind: str,
) -> dict[str, tuple[int, str]]:
    """Authenticate each new scoped setter from its real finite, committed source grant."""
    from girlframe.engine.m2 import TagState

    def tags(state: GameState) -> dict[tuple[ActorRef, str], TagState]:
        result = {
            (ActorRef(kind="pilot", entity=uid, incarnation=sheet.character_id), tag.id): tag
            for uid, sheet in state.sheets.items()
            if sheet.character_id
            for tag in sheet.tags
        }
        handler = active_handler(state)
        if handler:
            result.update({(handler, tag.id): tag for tag in state.handler_tags})
        from girlframe.engine.m3_harpy_defeat_state import NativeHarpyRuntime
        from girlframe.engine.m3_void_state import HarpyState

        bodies: list[HarpyState | NativeHarpyRuntime] = [*state.harpy_states, *state.native_harpies]
        for body in bodies:
            ref = ActorRef(kind="external_pilot", entity=body.id)
            result.update(
                {
                    (ref, tag.id): TagState.model_validate(
                        {k: v for k, v in tag.model_dump().items() if k != "giver_ref"}
                        | {"giver_actor": tag.giver_ref}
                    )
                    for tag in body.tags
                }
            )
        return result

    before, after = tags(previous), tags(staged)
    principals: dict[str, tuple[int, str]] = {}
    for (subject, identity), tag in after.items():
        if tag.gm_setter_grant is None:
            continue
        prior = before.get((subject, identity))
        if prior is None and subject.kind == "external_pilot":
            body = next(
                (
                    x
                    for x in staged.harpy_states
                    if x.id == subject.entity and x.source_event == event
                ),
                None,
            )
            if body is not None:
                from girlframe.engine.m3_tag_permissions import conversion

                _, marker = conversion(staged, subject)
                if identity in marker["retained_tag_ids"]:
                    prior = before.get((body.origin, identity))
        if prior is not None:
            fields = (
                "giver",
                "giver_actor",
                "giver_character",
                "gm_setter_appointment",
                "gm_setter_event",
                "gm_setter_grant",
            )
            if any(getattr(prior, k) != getattr(tag, k) for k in fields):
                raise WorkflowError(
                    "An existing scoped Tag cannot change its original human source."
                )
            continue
        _, original = _source(c, game, tag.gm_setter_grant)
        _authority(c, game, previous, original)
        grant = rules.record(staged, original.id)
        if (
            actor is None
            or kind != "m3.handler_play_applied"
            or original.source != "required"
            or not original.clause.startswith("all_out_assault.")
            or original.adjudicator_ref is None
            or original.adjudicator_source is None
            or original.state != "pending"
            or grant.chooser_actor is not None
            or grant.chooser_controller != actor
            or tag.giver != actor
            or grant.effect_event != event
            or grant.effect is None
            or grant.effect.kind != "tag"
            or grant.effect.target != subject
            or subject not in grant.targets
            or tag.label != grant.effect.tag
            or identity != grant.id + ":tag"
            or tag.gm_setter_appointment != grant.appointment
            or tag.gm_setter_event not in (None, event)
            or grant.appointment is None
        ):
            raise WorkflowError(
                "A scoped OOC Tag needs its actual human judge's exact source effect."
            )
        principals[grant.id] = (actor, grant.appointment)
    return principals
