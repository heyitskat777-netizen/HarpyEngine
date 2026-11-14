"""An actual nominated Processor Core keeps its original range/Frame proposal."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_required_plays as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def available(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> bool:
    from girlframe.services.m3_ankou import require_rule

    try:
        require_rule(game, c, state, actor, ankou.PROCESSOR)
    except (ValueError, WorkflowError):
        return False
    return True


def prove_recipe(
    game: GameService, c: Connection, state: GameState, value: rules.RequiredLink
) -> ankou.Proposal:
    from girlframe.services.m3_ankou import prove_proposal

    proposal = prove_proposal(game, c, state, value.recipe)
    original = prove_proposal(game, c, _history(c, game, value.event), value.recipe)
    if (
        value.rule != ankou.PROCESSOR
        or value.target != value.actor
        or proposal.actor != value.actor
        or fingerprint(proposal.cast) != fingerprint(value.cast)
        or original.action is not None
        or original.bound_event is not None
        or proposal.model_copy(update={"action": None, "bound_event": None}) != original
        or proposal.action != value.action
        or bool(proposal.bound_event) != bool(value.bound_event)
    ):
        raise WorkflowError("Preserve the actual own Processor proposal and exact required binding")
    return proposal


def link_recipe(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    key: str,
    task: ankou.Task,
    recipe: str,
) -> dict[str, Any]:
    from girlframe.services.m3_ankou import prove_proposal, require_rule
    from girlframe.services.p1_source_pause import require_ready

    proposal = prove_proposal(game, c, state, recipe)
    require_rule(game, c, state, task.actor, ankou.PROCESSOR)
    if (
        ankou.PLAY not in task.options
        or proposal.actor != task.actor
        or proposal.cast != task.cast
        or proposal.action
        or proposal.bound_event
        or proposal.frame != ankou.frame(state, task.actor)
    ):
        raise WorkflowError(
            "Select only this original actor's unperformed nominated Processor Core"
        )
    validate_current(game, c, state, proposal)
    require_ready(game, c, state, task.id)
    event = str(uuid4())
    link = rules.RequiredLink(
        id=rules.identity(task.id, recipe, event),
        source=task.id,
        recipe=recipe,
        rule="frame.ankou.processor-core",
        actor=task.actor,
        target=task.actor,
        cast=task.cast,
        event=event,
    )
    rules.put(state, link)
    game.event(
        c,
        viewer.user_id,
        key,
        "m3.required_play_linked",
        state,
        event_id=event,
        source=task.id,
        recipe=recipe,
        link=link.id,
    )
    return dict(id=link.id, source=task.id, recipe=recipe, revision=state.revision)


def menu_recipes(
    game: GameService, c: Connection, state: GameState, task: ankou.Task
) -> list[dict[str, Any]]:
    from girlframe.services.m3_ankou import prove_proposal

    if ankou.PLAY not in task.options or not available(game, c, state, task.actor):
        return []
    result = []
    for proposal in ankou.records(state, ankou.Proposal):
        if (
            proposal.actor != task.actor
            or proposal.cast != task.cast
            or proposal.action
            or proposal.frame != ankou.frame(state, task.actor)
        ):
            continue
        prove_proposal(game, c, state, proposal.id)
        try:
            validate_current(game, c, state, proposal)
        except (WorkflowError, ValueError):
            continue
        result.append(
            dict(
                id=proposal.id,
                rule=ankou.PROCESSOR,
                play=ankou.PLAY,
                label="Original Processor Core proposal " + proposal.id,
                target=task.actor.model_dump(mode="json"),
            )
        )
    return result


def validate_current(
    game: GameService, c: Connection, state: GameState, proposal: ankou.Proposal
) -> None:
    from girlframe.services import m3_ankou_support as support
    from girlframe.services.m3_ankou import _positions, require_rule
    from girlframe.services.m3_dose_up import _cast

    require_rule(game, c, state, proposal.actor, ankou.PROCESSOR)
    cast = _cast(game, c, state, proposal.cast.channel)
    support.cast_actor(game, c, state, cast, proposal.actor)
    minds = support.processor_minds(
        game, c, state, proposal.actor, proposal.exempt_cadre, proposal.exempt
    )
    if (
        proposal.action
        or proposal.bound_event
        or proposal.frame != ankou.frame(state, proposal.actor)
        or fingerprint(cast) != fingerprint(proposal.cast)
        or not minds
        or minds != proposal.minds
        or _positions(game, c, state, (proposal.actor, *minds)) != proposal.positions
        or any(
            x.actor == proposal.actor and not x.unlinked_event
            for x in ankou.records(state, ankou.Processor)
        )
    ):
        raise WorkflowError("Refresh the changed actual Processor minds, positions or Frame")


def withdraw(
    game: GameService, viewer: GuildViewer, key: str, identity: str, revision: int
) -> dict[str, Any]:
    """Release only unbound selection; the original performance remains owed."""
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_required_plays import RequiredPlayService, _access, prove

    def operation(c: Connection) -> dict[str, Any]:
        game.unpaused(c)
        state = load_state(c, game.store.campaign_id)
        value = prove(game, c, state, identity)
        task = RequiredPlayService(game)._owner(c, viewer, state, value.source)
        if state.revision != revision:
            raise WorkflowError("STALE_REQUIRED_PLAY: reopen the actual source")
        if (
            value.rule != ankou.PROCESSOR
            or value.action
            or value.bound_event
            or value.retired_event
            or value.completed_event
            or value.releases
            or task.child
            or task.completed_event
        ):
            raise WorkflowError(
                "Withdraw only the unprepared Processor selection, never its owed Play"
            )
        event = str(uuid4())
        rules.put(
            state, value.model_copy(update={"retired_event": event, "withdrawn_event": event})
        )
        game.event(
            c,
            viewer.user_id,
            key,
            "m3.required_processor_withdrawn",
            state,
            event_id=event,
            link=value.id,
            source=value.source,
            recipe=value.recipe,
        )
        return dict(id=value.id, source=value.source, revision=state.revision)

    return game.store._write(
        viewer,
        key,
        "m3.required_processor_withdrawn",
        dict(link=identity, revision=revision),
        operation,
        auto_audit=False,
        authorize=lambda c: _access(game, c, viewer),
    )


def prove_withdrawal(
    game: GameService, c: Connection, state: GameState, value: rules.RequiredLink
) -> None:
    import json

    import sqlalchemy as sa

    from girlframe.database import tables as t

    if (
        value.rule != ankou.PROCESSOR
        or not value.withdrawn_event
        or value.retired_event != value.withdrawn_event
        or value.action
        or value.bound_event
        or value.completed_event
        or value.releases
    ):
        raise WorkflowError("Preserve the actual unprepared Processor withdrawal")
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.withdrawn_event,
        )
    ).first()
    payload = json.loads(audit.payload_json) if audit else {}
    withdrawn = _history(c, game, value.withdrawn_event)
    if (
        audit is None
        or audit.kind != "m3.required_processor_withdrawn"
        or audit.actor_id != value.actor.entity
        or payload.get("link") != value.id
        or payload.get("source") != value.source
        or payload.get("recipe") != value.recipe
        or rules.get(withdrawn, value.id) != value
    ):
        raise WorkflowError("Preserve the original owner-authored Processor withdrawal event")
    prove_recipe(game, c, withdrawn, value)
    # Later reuse of this original unperformed proposal must not invalidate the
    # old withdrawal; it remains bound to its own historical event, not new links.
