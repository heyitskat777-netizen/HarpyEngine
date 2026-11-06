"""Printed Dive Deep changes actual resources; table answers are human service work."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import AssetState, GameState, IdentityState, PilotSheet, shift_status
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import Followup
from girlframe.engine.m3_dive_state import Effect
from girlframe.engine.m3_janus_storage import GainSource
from girlframe.engine.m3_physical import lock_cockpit
from girlframe.engine.m3_void_state import HarpyAsset, HarpyIdentity
from girlframe.engine.m3_world_state import Asset, WorldTag

PLAY = "dive_deep"


class Outcome(Model):
    state: GameState
    followups: tuple[Followup, ...] = ()


def nearby_all(state: GameState, actor: ActorRef, cast_npcs: tuple[str, ...]) -> tuple[str, ...]:
    if state.world is None:
        return ()
    body = next((x for x in state.placements if x.actor == actor), None)
    cell = body.girl_cell if body else None
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        cell = harpy(state, actor).cell
    if actor.kind == "npc":
        cell = next((x.cell for x in state.world.npcs if x.id == actor.entity), None)
    from girlframe.engine.m3_passengers import passenger_view

    passenger = passenger_view(state, actor)
    if passenger is not None:
        from girlframe.engine.m3_actors import frame_position

        cell = frame_position(state, passenger.carrier, passenger.frame, fallback=passenger.cell)
    return tuple(
        x.id
        for x in state.world.npcs
        if x.alive and (x.id in cast_npcs or cell is not None and x.cell == cell)
    )


def nearby(state: GameState, actor: ActorRef, cast_npcs: tuple[str, ...]) -> tuple[str, ...]:
    all_ids = nearby_all(state, actor, cast_npcs)
    return (
        tuple(x.id for x in state.world.npcs if x.id in all_ids and "director" not in x.jobs)
        if state.world
        else ()
    )


def nearby_directors(
    state: GameState, actor: ActorRef, cast_npcs: tuple[str, ...]
) -> tuple[ActorRef, ...]:
    all_ids = nearby_all(state, actor, cast_npcs)
    return (
        tuple(
            ActorRef(kind="npc", entity=x.id)
            for x in state.world.npcs
            if x.id in all_ids and "director" in x.jobs
        )
        if state.world
        else ()
    )


def resources(
    state: GameState, actor: ActorRef
) -> tuple[Sequence[AssetState | HarpyAsset | Asset], Sequence[IdentityState | HarpyIdentity]]:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("Recover the actual original Girl's resources")
        from girlframe.engine.m3_janus_storage import effective_assets

        return effective_assets(state, actor), sheet.identities
    from girlframe.engine.m3_harpy_defeat import harpy
    from girlframe.engine.m3_harpy_resources import assets

    return assets(state, actor), harpy(state, actor).identities


def sedation_locks(state: GameState, actor: ActorRef) -> frozenset[str]:
    if actor.kind == "pilot":
        return frozenset(state.sheets[actor.entity].sedation_locked)
    from girlframe.engine.m3_harpy_defeat import harpy
    from girlframe.engine.m3_void_state import HarpyState

    body = harpy(state, actor)
    if not isinstance(body, HarpyState):
        return frozenset()
    archived = next(
        (
            x
            for x in state.career_archives
            if x.id == body.original_archive and x.actor == body.origin and x.ending == "harpy"
        ),
        None,
    )
    if archived is None:
        raise ValueError("Recover the actual original Harpy conversion's retained source locks")
    return frozenset(PilotSheet.model_validate_json(archived.sheet_json).sedation_locked)


def _harpy_assets(
    state: GameState,
    actor: ActorRef,
    values: Sequence[AssetState | HarpyAsset | Asset],
    *,
    event: str,
) -> GameState:
    from girlframe.engine.m3_harpy_resources import set_assets

    return set_assets(state, actor, values, event=event)


def apply(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    option: str,
    effect: Effect,
    action: str,
    step: int,
    event: str,
    *,
    piloting: bool,
    handler: ActorRef | None,
    cast_npcs: tuple[str, ...],
    handler_controller: int | None = None,
    storage: GainSource | None = None,
) -> Outcome:
    state = GameState.model_validate_json(original.model_dump_json())
    view = resolve(state, actor, bindings, require_current_profile=False)
    if (
        not (
            actor.kind == "pilot"
            and view.rules == "girl_frame"
            or actor.kind == "external_pilot"
            and view.girl == "harpy"
        )
        or not event
        or not action
    ):
        raise ValueError("Dive Deep requires the actual original Girl or Harpy and source effect")
    if any(
        x.get("kind") == "dive_effect" and x.get("action") == action and x.get("step") == str(step)
        for x in state.facts
    ):
        raise ValueError("This actual Dive effect was already applied")
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    actual_assets, actual_identities = resources(state, actor)
    locks = sedation_locks(state, actor)
    required: tuple[Followup, ...] = ()
    default = Effect(account=effect.account)
    supplied = {
        k
        for k in type(effect).model_fields
        if k != "account" and getattr(effect, k) != getattr(default, k)
    }
    allowed = {
        "void_and_unmark_all": {"asset", "description", "growth"},
        "erase_identity_and_table_question": {"identity", "question"},
        "nearby_npcs_gain_void": {"npcs"},
        "table_replaces_identity": {"identity", "replacement"},
        "locked_cockpit_extraction_requires_frame_consent": set(),
    }.get(option)
    if allowed is None or supplied - allowed:
        raise ValueError("Supply only this chosen printed Dive effect's actual details")
    if option == "void_and_unmark_all":
        if effect.asset is None and effect.growth is None:
            raise ValueError("Choose an actual uncorrupted Asset")
        if sheet is not None:
            own_frame = (
                view.inside_frame is True and view.occupied_frame_instance == view.frame_instance
            )
            context = own_frame if view.inside_frame is not None else piloting
            from girlframe.engine.m3_janus_storage import alter

            state, required = alter(
                state,
                actor,
                effect.asset or "",
                effect.description,
                action,
                event,
                piloting=context,
                source=storage,
                step=step,
                growth=effect.growth,
            )
            sheet = state.sheets[actor.entity]
            for entry in sheet.identities:
                if entry.id not in locks:
                    entry.marked = False
            state.sheets[actor.entity] = sheet
            from girlframe.engine.m3_clone_am import additional_identities, unmark_additional

            selected_copy = tuple(
                x.id
                for x in additional_identities(state, sheet.owner)
                if x.marked and x.id not in locks
            )
            unmark_additional(state, sheet.owner, selected_copy)
        else:
            from girlframe.engine.m3_harpy_defeat import update
            from girlframe.engine.m3_harpy_resources import assets

            selected = next((x for x in actual_assets if x.id == effect.asset and not x.void), None)
            if selected is None or not effect.description.strip():
                raise ValueError("Rewrite an actual uncorrupted Harpy Asset when gaining Void")
            state = _harpy_assets(
                state,
                actor,
                tuple(
                    x.model_copy(update={"void": True, "description": effect.description})
                    if x.id == selected.id
                    else x
                    for x in assets(state, actor)
                ),
                event=event,
            )
            state = update(
                state,
                actor,
                identities=tuple(
                    x.model_copy(update={"marked": False}) if x.id not in locks else x
                    for x in actual_identities
                ),
            )
    elif option in ("erase_identity_and_table_question", "table_replaces_identity"):
        identity = next(
            (x for x in actual_identities if x.id == effect.identity and not x.protected), None
        )
        if identity is None:
            raise ValueError("Choose one current ordinary unprotected Identity")
        from girlframe.engine.m3_leviathan_obsession import require_identity_change

        require_identity_change(state, actor, (identity.id,))
        if option == "erase_identity_and_table_question":
            if not effect.question.strip():
                raise ValueError("Ask the actual question for the table")
            if sheet is not None:
                sheet.identities = [x for x in sheet.identities if x.id != identity.id]
            else:
                from girlframe.engine.m3_harpy_defeat import update

                state = update(
                    state,
                    actor,
                    identities=tuple(x for x in actual_identities if x.id != identity.id),
                )
        else:
            if not effect.replacement.strip():
                raise ValueError("The table must agree on an actual new Identity")
            if sheet is not None:
                pilot_identity = next(x for x in sheet.identities if x.id == identity.id)
                pilot_identity.name = effect.replacement.strip()
                if identity.id in locks:
                    pilot_identity.marked = True
            else:
                from girlframe.engine.m3_harpy_defeat import update

                state = update(
                    state,
                    actor,
                    identities=tuple(
                        x.model_copy(
                            update={
                                "name": effect.replacement.strip(),
                                "marked": True if x.id in locks else x.marked,
                            }
                        )
                        if x.id == identity.id
                        else x
                        for x in actual_identities
                    ),
                )
        if sheet is not None:
            sheet.revision += 1
    elif option == "nearby_npcs_gain_void":
        expected = nearby(state, actor, cast_npcs)
        if (not expected and not nearby_directors(state, actor, cast_npcs)) or {
            x.npc for x in effect.npcs
        } != set(expected):
            raise ValueError(
                "Apply one Handler-owned manifestation to every actual nearby living NPC"
            )
        controller = (
            handler_controller
            if handler_controller is not None
            else int(handler.entity)
            if handler
            else None
        )
        if controller is None:
            raise ValueError(
                "The actual source Handler or Director chooses NPC Void manifestations"
            )
        manifestations = {x.npc: x.manifestation for x in effect.npcs}
        if state.world is not None:
            state.world = state.world.model_copy(
                update={
                    "npcs": tuple(
                        npc.model_copy(
                            update={
                                "tags": npc.tags
                                + (
                                    WorldTag(
                                        id=str(uuid5(NAMESPACE_URL, event + ":" + npc.id)),
                                        label="Void of the " + manifestations[npc.id],
                                        giver_entity=handler.model_dump_json()
                                        if handler
                                        else "gm:" + str(controller) + ":" + event,
                                    ),
                                )
                            }
                        )
                        if npc.id in manifestations
                        else npc
                        for npc in state.world.npcs
                    )
                }
            )
    else:
        if actor.kind == "external_pilot":
            from girlframe.engine.m3_harpy_physical import lock

            state = lock(state, actor, event, effect.account)
        else:
            state = lock_cockpit(state, bindings, actor, event, effect.account)
    state.facts.append(
        dict(
            kind="dive_effect",
            action=action,
            step=str(step),
            actor=actor.model_dump_json(),
            option=option,
            source_event=event,
            account=effect.account,
            effect=effect.model_dump_json(),
        )
    )
    return Outcome(state=state, followups=required)


def high_status(original: GameState, actor: ActorRef, action: str, event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    if any(x.get("kind") == "dive_spike_status" and x.get("action") == action for x in state.facts):
        raise ValueError("This actual synchronicity spike already lowered Status")
    shift_status(state, int(actor.entity), -1)
    state.facts.append(
        dict(
            kind="dive_spike_status",
            action=action,
            source_event=event,
            actor=actor.model_dump_json(),
        )
    )
    return state
