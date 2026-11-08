"""Actual Director authority, finite endorsed consequences and real Court discipline."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.engine.m3_world import update
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_role_punishments import open_case
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _copy(state: GameState, other: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(other, name))


def _director(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> int:
    npc = next((x for x in state.world.npcs if x.id == actor.entity), None) if state.world else None
    if (
        actor.kind != "npc"
        or npc is None
        or not npc.alive
        or "director" not in npc.jobs
        or npc.employment == "unemployed"
        or npc.source_kind is not None
    ):
        raise WorkflowError(
            "Choose the actual original living Foundation Director, never a GM body alias"
        )
    history = t.m2["m2_state_history"]
    existed = False
    for raw in c.scalars(
        sa.select(history.c.body_json)
        .where(history.c.campaign_id == game.store.campaign_id)
        .order_by(history.c.revision)
    ):
        saved = GameState.model_validate_json(raw)
        if saved.world and any(
            x.id == npc.id and x.alive and "director" in x.jobs and x.controller == npc.controller
            for x in saved.world.npcs
        ):
            existed = True
            break
    if not existed:
        raise WorkflowError("The actual Director office/body/controller needs its canonical source")
    return resolve(state, actor, profiles(c, game.store.campaign_id)).controller


def _directors(
    game: GameService, c: Connection, state: GameState, human: int
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if state.world is None:
        return result
    visible_contexts = {
        key for context in state.director_contexts if context.active for key in context.directors
    }
    for npc in state.world.npcs:
        if (
            not npc.alive
            or "director" not in npc.jobs
            or npc.employment == "unemployed"
            or not (npc.revealed or npc.id in visible_contexts or npc.controller == human)
        ):
            continue
        ref = ActorRef(kind="npc", entity=npc.id)
        human = _director(game, c, state, ref)
        result.append(
            dict(id=ref.token, ref=ref.model_dump(mode="json"), label=npc.name, controller=human)
        )
    return result


def director_options(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer
) -> list[dict[str, Any]]:
    return _directors(game, c, state, viewer.user_id)


def accusation_targets(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer
) -> list[dict[str, Any]]:
    bound = profiles(c, game.store.campaign_id)
    result: list[dict[str, Any]] = []
    for sheet in state.sheets.values():
        ref = ActorRef(kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id)
        actual = resolve(state, ref, bound)
        if actual.alive:
            result.append(
                dict(id=ref.token, target=ref.entity, kind="girl", label="Girl: " + actual.label)
            )
    if state.world:
        result.extend(
            dict(
                id="location:" + x.id,
                target=x.id,
                kind=x.kind,
                label=x.kind.title() + ": " + x.name,
            )
            for x in state.world.locations
            if x.kind in ("city", "base") and x.allegiance == "foundation" and x.operational
        )
        result.extend(
            dict(id="npc:" + x.id, target=x.id, kind="npc", label="NPC: " + x.name)
            for x in state.world.npcs
            if x.alive and (x.revealed or x.controller == viewer.user_id)
        )
    return result


def validate_accusation(
    game: GameService, c: Connection, state: GameState, value: rules.Accusation
) -> dict[str, Any]:
    from girlframe.services.m3_red_queen import require_rule

    require_rule(game, c, state, value.actor, rules.ACCUSATION)
    court = rules.court(state, value.actor)
    if court.id != value.court:
        raise WorkflowError("Use the actual current original Court, not an unrelated Frame")
    receipt = next(
        (x for x in rules.held(state, value.actor, rules.ACCUSATION) if x.id == value.purchase),
        None,
    )
    if receipt is None:
        raise WorkflowError("Erase exactly one actual unspent Biting Accusation")
    purchase_proof(c, game.store, receipt)
    bound = profiles(c, game.store.campaign_id)
    author = resolve(state, value.actor, bound)
    if not author.alive:
        raise WorkflowError("Only the actual original living accuser chooses this source")
    # Knowledge selection is source-scoped, never an export of hidden World NPCs.
    candidates = _directors(game, c, state, author.controller)
    if value.director is None:
        if len(candidates) != 1:
            raise WorkflowError("Select the actual source Director when more than one is available")
        director = ActorRef.model_validate(candidates[0]["ref"])
    else:
        director = value.director
        if director.token not in {x["id"] for x in candidates}:
            raise WorkflowError("Choose an actual known source Director")
    controller = _director(game, c, state, director)
    target_actor = None
    if value.target_kind == "girl":
        sheet = state.sheets.get(value.target)
        if sheet is None:
            raise WorkflowError("Choose an actual original current Girl")
        target_actor = ActorRef(kind="pilot", entity=value.target, incarnation=sheet.character_id)
        if value.target_actor is not None and value.target_actor != target_actor:
            raise WorkflowError(
                "A successor cannot inherit an accusation against the original Girl"
            )
        from girlframe.engine.m3_intracadre_marriage import punishment_subject
        from girlframe.engine.m3_role_punishments import available

        subject = punishment_subject(state, target_actor)
        if (
            value.consequence_kind != "punishment"
            or value.consequence_detail.get("kind") not in ("stimulant_injection", "beating")
            or value.consequence_detail.get("kind")
            not in available(state, subject, value.actor, bound)
        ):
            raise WorkflowError(
                "SOURCE_CONSEQUENCE_REQUIRED: choose actual supported Girl discipline"
            )
    elif value.target_kind == "npc":
        npc = (
            next((x for x in state.world.npcs if x.id == value.target and x.alive), None)
            if state.world
            else None
        )
        label = value.consequence_detail.get("label", "")
        if (
            npc is None
            or not npc.revealed
            and npc.controller != author.controller
            or value.consequence_kind != "npc_tag"
            or not label.strip()
            or len(label) > 120
        ):
            raise WorkflowError(
                "SOURCE_CONSEQUENCE_REQUIRED: choose a known actual NPC and real Tag"
            )
        target_actor = ActorRef(kind="npc", entity=npc.id)
    else:
        location = (
            next(
                (
                    x
                    for x in state.world.locations
                    if x.id == value.target and x.kind == value.target_kind
                ),
                None,
            )
            if state.world
            else None
        )
        if (
            location is None
            or location.allegiance != "foundation"
            or not location.operational
            or value.consequence_kind != "administrative_closure"
            or not value.consequence_detail.get("account", "").strip()
        ):
            raise WorkflowError(
                "SOURCE_CONSEQUENCE_REQUIRED: choose an operational Foundation City/Base closure"
            )
    return dict(
        director=director.model_dump(mode="json"),
        director_controller=controller,
        target_actor=target_actor.model_dump(mode="json") if target_actor else None,
    )


def _case(
    game: GameService,
    c: Connection,
    state: GameState,
    source: rules.Breach | rules.Accusation,
    event: str,
    target: ActorRef,
) -> tuple[str, ...]:
    if source.actor == target:
        raise WorkflowError("Use actual separate discipline participants")
    identity = rules.identity("discipline", source.id)
    changed, case_id = open_case(
        state,
        profiles(c, game.store.campaign_id),
        actor=source.actor,
        target=target,
        chooser=source.actor,
        source_kind="red_queen",
        action=None,
        source_event=event,
        identity=identity,
        source_work=source.id,
    )
    _copy(state, changed)
    case = next(x for x in state.role_punishments if x.id == case_id)
    return (case.pc_work or case.id,)


def punishment(
    game: GameService, c: Connection, state: GameState, value: rules.Breach, event: str
) -> tuple[str, ...]:
    if value.event != event or rules.get(state, rules.Breach, value.id) != value:
        raise WorkflowError("Stage only the exact actual original Decree breach")
    return _case(game, c, state, value, event, value.target)


def endorse_accusation(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Accusation,
    viewer: GuildViewer,
    event: str,
) -> tuple[str, ...]:
    born = rules.get(_history(c, game, value.event), rules.Accusation, value.id)
    if (
        born.model_dump(exclude={"endorsement_event", "work", "completed_event"})
        != value.model_dump(exclude={"endorsement_event", "work", "completed_event"})
        or value.director is None
        or value.director_controller != viewer.user_id
        or _director(game, c, state, value.director) != viewer.user_id
    ):
        raise WorkflowError("Only the actual original Director player endorses this exact source")
    if value.endorsement_event:
        raise WorkflowError("Preserve the actual previously endorsed consequence")
    receipt = next((x for x in state.requisitions if x.id == value.purchase), None)
    if receipt is None:
        raise WorkflowError("Retain the immutable original erased purchase receipt")
    purchase_proof(c, game.store, receipt)
    if value.consequence_kind == "punishment":
        if value.target_actor is None or value.target_actor.kind != "pilot":
            raise WorkflowError("Preserve the actual original accused Girl")
        actual = resolve(state, value.target_actor, profiles(c, game.store.campaign_id))
        if not actual.alive:
            raise WorkflowError("SOURCE_ENDED_SUBJECT_REQUIRED: preserve the original accusation")
        return _case(game, c, state, value, event, value.target_actor)
    if value.consequence_kind == "npc_tag":
        if value.target_actor is None or value.target_actor.kind != "npc":
            raise WorkflowError("Use the actual original accused NPC")
        label = value.consequence_detail["label"]
        tag_id = rules.identity("accusation-tag", value.id)
        changed = give_tag(
            state,
            profiles(c, game.store.campaign_id),
            value.target_actor,
            value.director,
            label,
            tag_id,
            event,
            tuple(sorted({viewer.user_id, int(value.actor.entity)})),
        )
        _copy(state, changed)
    else:
        if state.world is None:
            raise WorkflowError("Recover the actual original operational location")
        location = next(
            (
                x
                for x in state.world.locations
                if x.id == value.target and x.kind == value.target_kind
            ),
            None,
        )
        if location is None or not location.operational or location.allegiance != "foundation":
            raise WorkflowError("Preserve the actual original Foundation location")
        blocker = "red-queen-closure:" + value.id
        state.world = update(
            state.world,
            locations=tuple(
                x.model_copy(update=dict(blocked_by=(*x.blocked_by, blocker)))
                if x.id == location.id
                else x
                for x in state.world.locations
            ),
        )
    state.facts.append(
        dict(
            kind="red_queen_accusation_effect",
            id=value.id,
            event=event,
            actor=value.director.model_dump_json(),
            target=value.target,
            consequence=value.consequence_kind,
            details=json.dumps(value.consequence_detail),
        )
    )
    return ()


def accusation_viewers(
    game: GameService, c: Connection, state: GameState, value: rules.Accusation
) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                int(value.actor.entity),
                *({value.director_controller} if value.director_controller is not None else set()),
            }
        )
    )


def official_allegations(
    state: GameState, kind: str, target: ActorRef | str
) -> list[dict[str, Any]]:
    """Official claims change Foundation belief, never the original OOC truth record."""
    return [
        dict(
            allegation=x.allegation,
            actor=x.actor.model_dump(mode="json"),
            endorsement=bool(x.endorsement_event),
        )
        for x in rules.records(state, rules.Accusation)
        if x.target_kind == kind
        and (
            x.target_actor == target
            if isinstance(target, ActorRef)
            else kind in ("city", "base") and x.target == target
        )
    ]
