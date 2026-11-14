"""Actual piloted Beneath damage retains its mandatory Defeat after Feedback."""

import json
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_core import damage
from girlframe.services.m3_ankou_alpha_counter import source_binding
from girlframe.services.m3_ankou_pin import _answer
from girlframe.services.m3_beneath import feedback_source_binding, roles
from girlframe.services.m3_disposable_psyche import _before
from girlframe.services.m3_dose_up import _cast, _native, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.engine.m3_ankou_feedback import Feedback
    from girlframe.services.m2_game import GameService
    from girlframe.services.read_only_bot import GuildViewer


def validate_required_defeat(
    game: "GameService",
    c: Connection,
    viewer: "GuildViewer",
    state: GameState,
    prepared: PlayInput,
    channel: int,
    value: "Feedback",
) -> None:
    """Defer only the original owner's proved last-Frame loss to ordinary Defeat."""
    parent = game.action(c, value.action)
    original = PlayInput.model_validate(parent["data"]["prepared"])
    if value.beneath_counter_source is None:
        if (
            original.parent is not None
            or parent.get("parent_id") is not None
            or original.source_work is not None
            or original.order_id is not None
            or original.off_duty_id is not None
            or any(
                parent["data"].get(key)
                for key in ("actor_basic", "princess_child", "m3", "alpha_counter_source")
            )
        ):
            raise WorkflowError("Preserve this original standalone native Beneath source")
    elif value.beneath_counter_source != source_binding(game, c, state, parent):
        raise WorkflowError("Preserve this original native Beneath counter source")
    declaration = feedback_source_binding(parent, counter_source=value.beneath_counter_source)
    roll, total = _roll_source(game, c, parent)
    setter, victim = roles(parent, "low")
    if (
        value.phase != "resolved"
        or value.choice != "purpose"
        or value.purpose_given is not True
        or not value.new_identity
        or not value.resolved_event
        or value.beneath_source != declaration
        or value.rolled_event != roll
        or value.receipt != parent["data"]["receipt"]["id"]
        or value.actor != victim
        or total >= 8
        or parent["data"]["result"].get("tier") != "low"
        or parent["state"] != "awaiting_choices"
        or not original.piloting
        or prepared.play != "defeat"
        or prepared.parent != parent["id"]
        or not prepared.piloting
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or prepared.target is not None
        or prepared.target_actor is not None
        or prepared.identity is not None
        or prepared.gain
        or prepared.heat
        or prepared.pair_share
        or prepared.disposable_heat
        or prepared.witnessed
        or not prepared.trigger_confirmed
        or prepared.learned_keep_rider is not None
        or prepared.prince_exception is not None
        or prepared.kicked_puppy_basis
        or viewer.user_id != int(victim.entity)
        or channel != int(parent["channel_id"])
        or _cast(game, c, state, channel) != value.cast
    ):
        raise WorkflowError("Use this original piloted Beneath source's actual required Defeat")
    selection, _, selected = _answer(game, c, parent, int(setter.entity), "beneath_select")
    details, event, detail = _answer(game, c, parent, int(victim.entity), "beneath_details")
    if (
        selected.options != ("damage",)
        or parent["data"]["result"].get("beneath_effects") != ["damage"]
        or json.loads(details["body_json"])
        != dict(options=["damage"], source_choice=selection["id"])
        or len(detail.denied) != 1
        or detail.options
        or detail.fields
        or detail.text
        or detail.flag is not None
        or detail.member is not None
        or detail.number is not None
    ):
        raise WorkflowError("Preserve both original owners' actual damage and Asset choices")
    before, after = _before(game, c, event), _history(c, game, event)
    choice = dict(
        kind="beneath_choice",
        action=parent["id"],
        choice=selection["id"],
        owner=setter.entity,
        owner_character=str(setter.incarnation),
        target=victim.entity,
        target_character=str(victim.incarnation),
        options="damage",
        text=selected.text,
    )
    for history in (before, after, state):
        for person in (setter, victim):
            actual = _native(game, c, history, person)
            if (
                not actual.alive
                or actual.controller != int(person.entity)
                or current_ref(history, int(person.entity)) != person
            ):
                raise WorkflowError("Preserve the original living people and native controllers")
        actual = _native(game, c, history, victim)
        if actual.piloting is not True or actual.frame_instance != value.frame:
            raise WorkflowError("Keep the actually piloted original Frame through this loss")
    asset = next((x for x in before.sheets[victim.entity].assets if x.id == detail.denied[0]), None)
    if asset is None or asset.family != "frame" or asset.damaged:
        raise WorkflowError("Prove the actual previously undamaged original Frame Asset")
    outcome = damage(before.sheets[victim.entity], asset.id, piloting=True)
    if (
        not any(x.kind == "defeat" for x in outcome.followups)
        or outcome.sheet.assets != after.sheets[victim.entity].assets
        or after.sheets[victim.entity].assets != state.sheets[victim.entity].assets
        or any(choice not in history.facts for history in (after, state))
    ):
        raise WorkflowError("Prove this canonical last-Frame damage and still-required Defeat")
    pending = [
        x
        for x in game.pending(c, parent["id"])
        if x["kind"] == "beneath_defeat" and x["actor_id"] == victim.entity
    ]
    work_id = str(
        uuid5(
            NAMESPACE_URL, "girlframe:beneath:" + parent["id"] + ":" + selection["id"] + ":defeat"
        )
    )
    if len(pending) != 1 or json.loads(pending[0]["body_json"]) != dict(
        owner=victim.model_dump(mode="json"),
        target=setter.model_dump(mode="json"),
        work_id=work_id,
    ):
        raise WorkflowError("Recover this original affected Pilot's pending Defeat requirement")
