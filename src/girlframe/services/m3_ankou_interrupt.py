"""Actual Emotional Relay interruption through the owner's ordinary Dive."""

from sqlalchemy import Connection

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def options(game: GameService) -> tuple[str, ...]:
    supported: tuple[str, ...] = (
        "keep_your_head",
        "check_sensors",
        "flirt",
        "all_out_assault",
        "engage",
        "put_someone_beneath_you",
    )
    registry = Access(game.store).registry
    if registry is not None:
        try:
            registry.require_available("play.basic.dive_deep")
        except ValueError:
            pass
        else:
            supported += ("dive_deep",)
    return supported


def prepare_dive(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> bool:
    task = next(
        (
            x
            for x in rules.records(state, rules.Task)
            if x.id == prepared.source_work and x.kind == "interrupt"
        ),
        None,
    )
    if task is None:
        return False
    from girlframe.services.m3_ankou import prove_relay, prove_task
    from girlframe.services.m3_ankou_feedback_sequences import prepare_child
    from girlframe.services.m3_ankou_support import actual_action_actor
    from girlframe.services.m3_asset_loss import snapshots

    task = prove_task(game, c, state, task.id)
    relay = prove_relay(game, c, state, task.source)
    if (
        prepared.play != "dive_deep"
        or prepared.target is not None
        or prepared.target_actor is not None
        or task.actor != current_ref(state, viewer.user_id)
        or task.controller != viewer.user_id
        or task.actor != relay.actor
        or task.cast != relay.cast
        or relay.ended_event
        or "interrupt" not in relay.benefits
        or task.choice != "interrupt"
        or task.options != ("dive_deep",)
        or not task.selected_event
        or not task.source_tag
        or task.target is None
        or task.source_action is None
        or task.request is None
        or prepared.parent != task.source_action
    ):
        raise WorkflowError("Use this exact owned Relay interruption and your own actual Dive")
    incoming = game.action(c, task.source_action)
    before, after = snapshots(game, c, task.selected_event)
    if (
        actual_action_actor(incoming) != task.target
        or incoming["scene_id"] != task.cast.id
        or int(incoming["channel_id"]) != channel
        or incoming["state"] == "complete"
        or not any(x.id == task.source_tag for x in actor_tags(before, task.target))
        or any(x.id == task.source_tag for x in actor_tags(after, task.target))
    ):
        raise WorkflowError("Preserve the genuine incoming person, held Play and original Tag cost")
    source = prepare_child(game, c, viewer, state, prepared, channel)
    if source is None or source["parent"] != incoming["id"] or source["choice"] != task.request:
        raise WorkflowError("Keep the actual pending interruption row and source-bound child")
    return True
