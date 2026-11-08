"""Real state transitions feeding CONSUME's printed hunger and original carrier position."""

from typing import Any

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles


def before_write(
    game: GameService,
    c: Connection,
    before: GameState,
    state: GameState,
    event: str,
    metadata: dict[str, Any],
) -> None:
    from girlframe.engine.m3_consume import InternalCustody, MouthHold, records
    from girlframe.services.m3_consume_support import follow_carriers

    if any(not x.escaped_event for x in records(state, InternalCustody)) or any(
        not x.ended_event for x in records(state, MouthHold)
    ):
        follow_carriers(game, c, before, state, event)
    if not any(x.frame == "CONSUME" for x in state.sheets.values()):
        return
    from girlframe.services.m3_access import Access, digest

    approval = game.store.policy.m3_approval
    if (
        approval is None
        or "plays" not in approval.subsystems
        or game.store.policy.owner_m3_rulings is None
    ):
        return
    registry = Access(game.store).registry
    if registry is None or digest(registry) != approval.registry_sha256:
        return
    try:
        registry.require_available("frame.consume.starvation")
    except ValueError:
        return
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_consume import stage_helpless, stage_link

    bound = profiles(c, game.store.campaign_id)
    for owner, sheet in state.sheets.items():
        old = before.sheets.get(owner)
        if sheet.frame != "CONSUME" or old is None or old.character_id != sheet.character_id:
            continue
        actor = current_ref(state, int(owner))
        actual = resolve(state, actor, bound, require_alive=False, require_current_profile=False)
        prior = resolve(before, actor, bound, require_alive=False, require_current_profile=False)
        if not actual.alive:
            continue
        if actual.piloting is True and (
            prior.piloting is not True
            or prior.occupied_frame_instance != actual.occupied_frame_instance
        ):
            assert actual.frame_instance is not None
            stage_link(game, c, state, actor, actual.frame_instance, event)
    subjects = {x.subject for x in (*before.helpless_conditions, *state.helpless_conditions)}
    subjects |= {
        current_ref(state, int(uid))
        for uid, sheet in state.sheets.items()
        if uid in before.sheets and sheet.character_id == before.sheets[uid].character_id
    }
    channel = metadata.get("channel")
    action_id = metadata.get("action_id")
    if channel is None and action_id:
        channel = int(game.action(c, action_id)["channel_id"])
    for subject in sorted(subjects, key=lambda x: x.token):
        stage_helpless(
            game, c, before, state, subject, event, channel=int(channel) if channel else None
        )


def roll_modifiers(
    game: GameService, c: Connection, state: GameState, actor: Any, prepared: Any
) -> list[dict[str, Any]]:
    from girlframe.engine import m3_consume as rules
    from girlframe.services.m3_consume import _prove_feral, require_rule, roll_basis

    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.frame != "CONSUME":
        if prepared.consume_seek_food:
            from girlframe.services.onboarding import WorkflowError

            raise WorkflowError("Only actual CONSUME starvation supplies this food-seeking basis")
        return []
    if game.store.policy.m3_approval is None:
        return []
    require_rule(game, c, state, actor, rules.STARVATION)
    basis = roll_basis(
        state, actor, prepared.play, prepared.heat, seek_food=prepared.consume_seek_food
    )
    result = []
    if prepared.play not in ("consume_eat", "consume_feral") and basis != prepared.heat:
        result.append(dict(source="consume_starvation_food", amount=basis - prepared.heat))
    bonus = rules.feral_bonus(state, actor, prepared.play)
    if bonus:
        for effect in rules.feral_effects(state, actor):
            _prove_feral(game, c, state, effect)
        result.append(dict(source="consume_feral_tag", amount=bonus))
    return result


def smell_question(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> str | None:
    from girlframe.services.m3_consume import acting, sensor_question

    actor = acting(state, action)
    return sensor_question(game, c, state, actor) if actor is not None else None


def starvation(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], marker: Any
) -> dict[str, Any] | None:
    from girlframe.services.m3_consume import acting, starvation_source
    from girlframe.services.m3_enforcement_initiative import _cast

    actor = acting(state, action)
    if actor is None or marker is None:
        return None
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.frame != "CONSUME":
        return None
    return starvation_source(
        game, c, state, actor, marker, _cast(game, c, state, int(action["channel_id"]))
    )
