"""Source-owned memory loss, legal original Identity replacement and actual restoration."""

from sqlalchemy import Connection

from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_identity_slots import bind
from girlframe.engine.m3_leviathan_obsession import require_unlocked
from girlframe.services.m2_game import GameService
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.onboarding import WorkflowError


def extract_memories(
    game: GameService,
    c: Connection,
    state: GameState,
    values: tuple[rules.Extraction, ...],
    event: str,
) -> tuple[str, ...]:
    if not values:
        raise WorkflowError("Choose the actual source memory category")
    first = values[0]
    if any(value.event != event or value.court != first.court for value in values):
        raise WorkflowError("Keep the original compound memory source and effect event")
    changed = GameState.model_validate_json(state.model_dump_json())
    if first.target.kind == "npc":
        rules.extract_many(changed, values)
        verified = GameState.model_validate_json(changed.model_dump_json())
        for name in GameState.model_fields:
            setattr(state, name, getattr(verified, name))
        return ()
    if first.target.kind != "pilot":
        raise WorkflowError("SOURCE_MEMORY_BODY_REQUIRED: use an actual supported original body")
    sheet = changed.sheets.get(first.target.entity)
    if sheet is None or sheet.character_id != first.target.incarnation:
        raise WorkflowError("Preserve the actual affected original person")
    ids = tuple(dict.fromkeys(key for value in values for key in value.identities))
    if any(key in sheet.sedation_locked for key in ids):
        raise WorkflowError("SOURCE_IDENTITY_REMOVAL_REQUIRED: preserve actual sedation locks")
    require_unlocked(sheet.identities, ids)
    changed.sheets[first.target.entity] = bind(sheet)
    rules.extract_many(changed, values)
    verified = GameState.model_validate_json(changed.model_dump_json())
    for name in GameState.model_fields:
        setattr(state, name, getattr(verified, name))
    return ()


def association_source(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Extraction,
    source_event: str,
    source_id: str,
    account: str,
) -> None:
    from girlframe.services.m3_red_queen import prove_extraction

    prove_extraction(game, c, state, value.id)
    if not value.low or value.restored_event or not account.strip() or len(account) > 1200:
        raise WorkflowError("Use only the genuine low-result subsequent memory association")
    before, after = snapshots(game, c, source_event)
    from girlframe.services.m3_handler_advancements import _history

    source_revision = _history(c, game, value.event).revision
    if after.revision <= source_revision or before.revision < source_revision:
        raise WorkflowError("The association must genuinely follow the original extraction")
    if value.target.kind == "pilot":
        first = before.sheets.get(value.target.entity)
        second = after.sheets.get(value.target.entity)
        current = state.sheets.get(value.target.entity)
        if (
            first is None
            or second is None
            or current is None
            or any(x.character_id != value.target.incarnation for x in (first, second, current))
        ):
            raise WorkflowError("Use the actual original affected Girl, never a replacement")
        if (
            any(x.id == source_id for x in first.identities)
            or not any(x.id == source_id for x in second.identities)
            or not any(x.id == source_id for x in current.identities)
        ):
            raise WorkflowError(
                "Choose an actual newly gained current Identity with its true source event"
            )
    elif value.target.kind == "npc":
        if before.world is None or after.world is None:
            raise WorkflowError("Recover the actual original NPC memory body")
        old = next((x for x in before.world.npcs if x.id == value.target.entity), None)
        new = next((x for x in after.world.npcs if x.id == value.target.entity and x.alive), None)
        if (
            old is None
            or new is None
            or any(x.id == source_id for x in old.tags)
            or not any(x.id == source_id for x in new.tags)
        ):
            raise WorkflowError("Choose the actual new associated NPC Tag, never a PC alias")
    else:
        raise WorkflowError(
            "SOURCE_MEMORY_ASSOCIATION_REQUIRED: use an actual supported body source"
        )
