"""Finite original-body NPC contact for native and genuinely earned Alpha sources."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_alpha_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_npc import NARRATIVE
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_dose_up import _audit
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_oldgen_sex import _npc_space
from girlframe.services.onboarding import WorkflowError


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
    _audit(game, c, contact.event, ("m3.alpha_sex_consent",), contact.controller)
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


def contact(
    game: GameService, c: Connection, state: GameState, value: rules.Session, own: Any, other: Any
) -> None:
    if value.bonded_source or value.changeling_source:
        raise WorkflowError("Keep NPC Alpha independent of delegated or psychic sources")
    if value.learned_source is not None:
        from girlframe.services.m3_learned_sex import admit_source

        if not admit_source(
            game, c, state, value.actor, value.target, rules.RULE, value.learned_source
        ):
            raise WorkflowError("Recover the exact earned lesson and original NPC source")
    _npc_space(game, c, state, other)
    if own.inside_frame is not False or own.cell is None or own.cell != other.cell:
        raise WorkflowError("Preserve actual original bodies together for this invitation")
    if value.phase not in ("invited", "declined"):
        _prove_npc_contact(game, c, value)
        assert value.npc_contact is not None
        if other.cell != value.npc_contact.cell:
            raise WorkflowError("Renew actual NPC contact after movement")


def plays(game: GameService, state: GameState, value: rules.Session) -> list[dict[str, str]]:
    """Reuse the finite job catalog without borrowing another opportunity's authority."""
    from girlframe.services.m3_access import Access

    if value.target.kind != "npc" or state.world is None:
        return []
    npc = next((x for x in state.world.npcs if x.id == value.target.entity and x.alive), None)
    if npc is None or npc.controller != value.counterpart:
        return []
    registry = Access(game.store).registry
    assert registry is not None
    supported = []
    for job in npc.jobs:
        if job not in NARRATIVE:
            continue
        try:
            registry.require_available("npc.npc." + job.replace("_", "-"))
        except ValueError:
            continue
        supported.append(dict(id=job, move=NARRATIVE[job][0]))
    return supported


def _choice(
    game: GameService,
    c: Connection,
    value: rules.Session,
    identity: str,
    event: str,
    kind: str,
) -> ChoiceAnswer:
    """Prove an Alpha-owned answer, never another NPC Play's source or a freeform ack."""
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id, choices.c.id == identity
            )
        )
        .mappings()
        .first()
    )
    response = (
        c.execute(
            sa.select(responses).where(
                responses.c.campaign_id == game.store.campaign_id, responses.c.choice_id == identity
            )
        )
        .mappings()
        .first()
    )
    if (
        audit is None
        or audit["kind"] != "m3.choice_resolved"
        or audit["actor_id"] != str(value.counterpart)
        or json.loads(audit["payload_json"]).get("action_id") != value.action
        or json.loads(audit["payload_json"]).get("choice_id") != identity
        or row is None
        or row["kind"] != kind
        or row["action_id"] != value.action
        or row["actor_id"] != str(value.counterpart)
        or row["state"] != "answered"
        or response is None
        or response["actor_id"] != str(value.counterpart)
        or response["event_id"] != event
    ):
        raise WorkflowError("Recover this original NPC controller's actual Alpha choice and event")
    return ChoiceAnswer.model_validate_json(response["answer_json"])


def selected(
    game: GameService, c: Connection, value: rules.Session, choice: str, event: str
) -> None:
    answer = _choice(game, c, value, choice, event, "alpha_sex_low")
    born = rules.get(_history(c, game, event), value.id)
    if (
        answer != ChoiceAnswer(options=("play",))
        or born.action != value.action
        or born.actor != value.actor
        or born.target != value.target
        or born.counterpart != value.counterpart
        or born.cast != value.cast
        or born.phase != "sleeping"
        or born.sleep_event != value.sleep_event
        or born.wake_event is not None
        or born.npc_performance is not None
    ):
        raise WorkflowError("Preserve this exact low-result NPC Play selection and sleeping source")


def perform(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Session,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> rules.NpcPerformance:
    from girlframe.engine.m3_actor_bonds import is_helpless
    from girlframe.services.m3_enforcement_initiative import _cast

    meta = action["data"]["alpha_sex"]
    if (
        value.target.kind != "npc"
        or value.action != action["id"]
        or value.phase != "sleeping"
        or not value.sleep_event
        or value.wake_event is not None
        or value.npc_performance is not None
        or action["data"]["result"]["tier"] != "low"
        or meta.get("opportunity") != "play"
        or meta.get("phase") != "npc_play"
        or request["actor_id"] != str(value.counterpart)
        or is_helpless(state, value.target)
        or _cast(game, c, state, value.cast.channel) != value.cast
    ):
        raise WorkflowError("Use this original capable NPC's pending sleeping-Alpha opportunity")
    selected(game, c, value, meta.get("selection_choice", ""), meta.get("selection_event", ""))
    if (
        len(answer.options) != 1
        or set(answer.fields) != {"move"}
        or not answer.text.strip()
        or not any(
            x["id"] == answer.options[0] and x["move"] == answer.fields["move"]
            for x in plays(game, state, value)
        )
    ):
        raise WorkflowError(
            "Perform one supported actual NPC job move; no invented damage, healing or movement"
        )
    event = action["data"]["response_event"]
    return rules.NpcPerformance(
        id="alpha-npc-performance:" + event,
        session=value.id,
        action=action["id"],
        actor=value.target,
        controller=value.counterpart,
        cast=value.cast,
        recipients=tuple(x for x in value.cast.roles if x.actor == value.actor),
        job=answer.options[0],
        move=answer.fields["move"],
        rendition=answer.text,
        selection_choice=meta["selection_choice"],
        selection_event=meta["selection_event"],
        choice=request["id"],
        event=event,
    )


def prove_performance(
    game: GameService, c: Connection, state: GameState, value: rules.Session
) -> rules.NpcPerformance:
    performance = value.npc_performance
    if performance is None:
        raise WorkflowError("Recover the actual performed NPC Conversation")
    selected(game, c, value, performance.selection_choice, performance.selection_event)
    born = _history(c, game, performance.event)
    original = rules.get(born, value.id)
    answer = _choice(game, c, value, performance.choice, performance.event, "alpha_sex_npc_play")
    action = game.action(c, value.action or "")
    meta = action["data"]["alpha_sex"]
    npc = (
        next((x for x in born.world.npcs if x.id == value.target.entity), None)
        if born.world
        else None
    )
    if (
        rules.get(state, value.id).npc_performance != performance
        or original.npc_performance != performance
        or original.phase != "waking"
        or original.sleep_event != value.sleep_event
        or original.wake_event is not None
        or performance.session != value.id
        or performance.action != value.action
        or performance.actor != value.target
        or performance.actor.kind != "npc"
        or performance.controller != value.counterpart
        or performance.cast != value.cast
        or performance.recipients != tuple(x for x in value.cast.roles if x.actor == value.actor)
        or len(performance.recipients) != 1
        or npc is None
        or not npc.alive
        or npc.controller != performance.controller
        or performance.job not in npc.jobs
        or performance.job not in NARRATIVE
        or performance.move != NARRATIVE[performance.job][0]
        or not performance.rendition.strip()
        or answer
        != ChoiceAnswer(
            options=(performance.job,),
            fields={"move": performance.move},
            text=performance.rendition,
        )
        or action["data"]["result"]["tier"] != "low"
        or meta.get("opportunity") != "play"
        or meta.get("selection_choice") != performance.selection_choice
        or meta.get("selection_event") != performance.selection_event
        or meta.get("npc_performance") != performance.id
    ):
        raise WorkflowError("Preserve the genuine Alpha-owned NPC job, rendition and recipient")
    return performance
