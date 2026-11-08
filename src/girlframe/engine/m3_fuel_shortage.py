"""A real fuel shortage waits for one actual Cadre battle, then causes its own loss."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle import end_actor_casts
from girlframe.engine.m3_battle_state import Context
from girlframe.engine.m3_collateral import install_budget, stage_loss
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_npc_void import npc_void_tag
from girlframe.engine.m3_physical import interrupt_journeys
from girlframe.engine.m3_world import destroy, update
from girlframe.engine.m3_world_state import Location, Npc, WorldLoss

RULE = "strain.budget.high.1.2"


class LossSelection(Model):
    source: str = Field(min_length=1)
    npc: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    location: str | None = Field(default=None, min_length=1, exclude_if=lambda value: value is None)
    account: str = Field(min_length=1, max_length=1200)
    npc_outcome: Literal["die", "capture", "corrupt"] = Field(
        default="die", exclude_if=lambda value: value == "die"
    )
    location_outcome: Literal["destroy", "capture", "corrupt"] = Field(
        default="destroy", exclude_if=lambda value: value == "destroy"
    )
    threat: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    manifestation: Literal["brain", "bones", "flesh", "abstract"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    manifestation_source: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def actual_loss(self) -> "LossSelection":
        if (
            (self.npc is None and self.location is None)
            or (self.npc is not None and self.npc.kind != "npc")
            or not self.account.strip()
        ):
            raise ValueError("Choose a real ordinary NPC and/or actual site loss")
        needs_threat = bool(
            (self.npc is not None and self.npc_outcome != "die")
            or (self.location is not None and self.location_outcome != "destroy")
        )
        if (
            (self.npc is None and self.npc_outcome != "die")
            or (self.location is None and self.location_outcome != "destroy")
            or needs_threat != (self.threat is not None)
            or (self.threat is not None and self.threat.kind != "gorgon")
            or (
                (self.npc is not None and self.npc_outcome == "corrupt")
                != (self.manifestation is not None)
            )
            or (self.manifestation_source is not None and self.manifestation is None)
        ):
            raise ValueError("Keep the exact actual threat and printed NPC Void manifestation")
        return self


class ManifestationChoice(Model):
    id: str
    source: str
    context: str
    proposed_event: str
    target: ActorRef
    threat: ActorRef
    manifestation: Literal["brain", "bones", "flesh", "abstract"]
    handler: ActorRef
    event: str

    @model_validator(mode="after")
    def original_people(self) -> "ManifestationChoice":
        if (
            self.target.kind != "npc"
            or self.threat.kind != "gorgon"
            or self.handler.kind != "handler"
        ):
            raise ValueError("Keep the actual Handler, NPC and Gorgon manifestation source")
        return self


def manifestations(state: GameState) -> tuple[ManifestationChoice, ...]:
    return tuple(
        ManifestationChoice.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "fuel_manifestation"
    )


def current_manifestations(
    state: GameState, source: str, context: str
) -> tuple[ManifestationChoice, ...]:
    latest: dict[tuple[ActorRef, ActorRef], ManifestationChoice] = {}
    for value in manifestations(state):
        if value.source == source and value.context == context:
            latest[value.target, value.threat] = value
    return tuple(latest.values())


class Arm(Model):
    id: str
    source_event: str
    period: str
    handler: ActorRef
    cadre: tuple[ActorRef, ...] = Field(min_length=1)
    event: str
    battle: str | None = None
    battle_event: str | None = None
    loss: LossSelection | None = None
    original_npc: Npc | None = None
    original_location: Location | None = None
    completed_event: str | None = None

    @model_validator(mode="after")
    def original_source(self) -> "Arm":
        if (
            self.handler.kind != "handler"
            or len(set(self.cadre)) != len(self.cadre)
            or any(x.kind != "pilot" for x in self.cadre)
            or (self.battle is None) != (self.battle_event is None)
            or (self.battle is None) != (self.loss is None)
            or (self.loss is not None and self.loss.source != self.id)
            or (self.completed_event is not None and self.battle is None)
        ):
            raise ValueError("Preserve the real source, Cadre and once-only battle loss")
        if self.loss and (
            (self.loss.npc is None) != (self.original_npc is None)
            or (self.loss.location is None) != (self.original_location is None)
        ):
            raise ValueError("Keep each actually lost original body/site")
        return self

    @property
    def phase(self) -> str:
        return "complete" if self.completed_event else "loss" if self.battle else "armed"


def records(state: GameState) -> tuple[Arm, ...]:
    return tuple(
        Arm.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "fuel_shortage"
    )


def npc_void_tags(state: GameState, target: ActorRef) -> tuple[str, ...]:
    """Actual bound Fuel Void points; callers still check the Tag is currently present."""
    return tuple(
        "fuel:void:" + value.id
        for value in records(state)
        if value.battle_event is not None
        and value.loss is not None
        and value.loss.npc == target
        and value.loss.npc_outcome == "corrupt"
        and value.original_npc is not None
    )


def put(state: GameState, value: Arm) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == "fuel_shortage" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="fuel_shortage", id=value.id, body=value.model_dump_json()))


def involves(value: Arm, context: Context) -> bool:
    return context.source_action is None and bool(
        set(value.cadre).intersection((context.declaration.actor, context.declaration.target))
    )


def threats(
    state: GameState, context: Context, bindings: tuple[ProfileBinding, ...]
) -> tuple[ActorRef, ...]:
    if state.world is None:
        return ()
    cells = {
        resolve(state, actor, bindings, require_current_profile=False).cell
        for actor in (context.declaration.actor, context.declaration.target)
    } - {None}
    cast = next((x for x in state.scene_casts if x.id == context.scene and x.open), None)
    cast_refs = {x.actor for x in cast.roles} if cast else set()
    return tuple(
        actor
        for gorgon in state.world.gorgons
        if gorgon.alive
        and (
            context.adjudicator == state.handler
            or gorgon.revealed
            or ActorRef(kind="gorgon", entity=gorgon.id) in cast_refs
        )
        and (actor := ActorRef(kind="gorgon", entity=gorgon.id))
        and resolve(state, actor, bindings, require_current_profile=False).cell in cells
    )


def candidates(
    state: GameState, context: Context, bindings: tuple[ProfileBinding, ...]
) -> tuple[tuple[Npc, ...], tuple[Location, ...]]:
    if state.world is None:
        return (), ()
    combatants = (context.declaration.actor, context.declaration.target)
    cells = {
        view.cell
        for actor in combatants
        if (view := resolve(state, actor, bindings, require_current_profile=False)).cell is not None
    }
    cast = next((x for x in state.scene_casts if x.id == context.scene and x.open), None)
    cast_refs = {x.actor for x in cast.roles} if cast else set()
    npcs = []
    for npc in state.world.npcs:
        actor = ActorRef(kind="npc", entity=npc.id)
        if (
            not npc.alive
            or npc.source_kind is not None
            or actor in combatants
            or npc.cell not in cells
            or any(x.asset_owner == actor for x in state.held_items)
            or any(
                actor in (x.subject, x.executor, x.chooser)
                and not x.completion_event
                and not x.ended_event
                for x in state.role_punishments
            )
            or not (
                context.adjudicator == state.handler
                or npc.controller == context.adjudicator
                or npc.revealed
                or actor in cast_refs
            )
        ):
            continue
        actual = resolve(state, actor, bindings, require_current_profile=False)
        if (
            actual.rules == "npc"
            and actual.cell in cells
            and actual.custody is None
            and not actual.assets
            and not actual.identities
        ):
            npcs.append(npc)
    locations = tuple(
        x
        for x in state.world.locations
        if x.cell in cells
        and x.condition != "destroyed"
        and x.ship is None
        and not x.protection_sources
    )
    return tuple(npcs), locations


def bind(
    original: GameState,
    value: Arm,
    context: Context,
    selection: LossSelection,
    event: str,
    bindings: tuple[ProfileBinding, ...],
) -> GameState:
    if value.battle or selection.source != value.id or not involves(value, context):
        raise ValueError("This exact fuel shortage binds once to its actual next Cadre battle")
    if context.state != "confirmed" or context.confirmed_event != event:
        raise ValueError("Bind loss to the genuine prospective battle confirmation")
    npcs, locations = candidates(original, context, bindings)
    npc = next((x for x in npcs if selection.npc and x.id == selection.npc.entity), None)
    location = next((x for x in locations if x.id == selection.location), None)
    if (selection.npc is not None and npc is None) or (
        selection.location is not None and location is None
    ):
        raise ValueError(
            "Choose actual supported loss at this battle: no combatant, special body, "
            "Ship Base or protected site"
        )
    if selection.threat is not None:
        if selection.threat not in threats(original, context, bindings):
            raise ValueError("Choose the real living, actually placed threat at this battle")
        threat = resolve(original, selection.threat, bindings, require_current_profile=False)
        if (npc is not None and selection.npc_outcome != "die" and npc.cell != threat.cell) or (
            location is not None
            and selection.location_outcome != "destroy"
            and location.cell != threat.cell
        ):
            raise ValueError(
                "Prove the actual threat's physical proximity to each affected endpoint"
            )
    if npc is not None and selection.npc_outcome == "corrupt":
        if selection.manifestation_source is not None:
            choice = next(
                (
                    x
                    for x in reversed(manifestations(original))
                    if x.source == value.id
                    and x.context == context.id
                    and x.target == selection.npc
                    and x.threat == selection.threat
                ),
                None,
            )
            if (
                choice is None
                or choice.id != selection.manifestation_source
                or choice.proposed_event != context.proposed_event
                or choice.target != selection.npc
                or choice.threat != selection.threat
                or choice.manifestation != selection.manifestation
            ):
                raise ValueError("Recover the actual Handler's exact saved manifestation choice")
        elif active_handler(original) is None or context.adjudicator != original.handler:
            raise ValueError(
                "HANDLER_MANIFESTATION_PENDING: the actual Handler chooses on the saved Fuel card"
            )
    if location is not None and selection.location_outcome != "destroy" and location.control_loss:
        raise ValueError("This site already has its actual control loss; choose a new real loss")
    state = original.model_copy(deep=True)
    if npc is not None:
        assert selection.npc is not None and state.world is not None
        changed_npc = npc.model_copy(update=dict(alive=False))
        if selection.npc_outcome == "capture":
            assert selection.threat is not None
            changed_npc = npc.model_copy(
                update=dict(
                    captive_of=selection.threat.entity,
                    custody_event=event,
                )
            )
        elif selection.npc_outcome == "corrupt":
            assert selection.threat is not None and selection.manifestation is not None
            changed_npc = npc.model_copy(
                update=dict(
                    tags=npc.tags
                    + (
                        npc_void_tag(
                            "fuel:void:" + value.id,
                            selection.manifestation,
                            selection.threat.model_dump_json(),
                        ),
                    )
                )
            )
        if selection.npc_outcome != "corrupt":
            state = interrupt_journeys(state, selection.npc, event, selection.account)
            state = end_actor_casts(state, selection.npc, event)
        assert state.world is not None
        state.world = update(
            state.world,
            npcs=tuple(changed_npc if x.id == npc.id else x for x in state.world.npcs),
        )
    if location is not None:
        assert state.world is not None
        if selection.location_outcome != "destroy":
            assert selection.threat is not None
            state.world = update(
                state.world,
                locations=tuple(
                    x.model_copy(
                        update=dict(
                            control_loss=WorldLoss(
                                source=value.id,
                                event=event,
                                kind="captured"
                                if selection.location_outcome == "capture"
                                else "corrupted",
                                threat=selection.threat,
                                account=selection.account,
                            )
                        )
                    )
                    if x.id == location.id
                    else x
                    for x in state.world.locations
                ),
            )
        else:
            state.world = destroy(state.world, location.id, gorgon_cause=False).world
            state.facts.append(
                dict(
                    kind="structure_destroyed_source",
                    id=value.id + ":site:" + event,
                    entity=location.id,
                    event=event,
                    source=value.id,
                )
            )
            install_budget(state)
            stage_loss(
                original,
                state,
                source=value.id,
                event=event,
                judge=context.adjudicator,
                appointment=context.appointment,
                handler=active_handler(original),
            )
    changed = value.model_copy(
        update=dict(
            battle=context.id,
            battle_event=event,
            loss=selection,
            original_npc=npc,
            original_location=location,
        )
    )
    put(state, Arm.model_validate_json(changed.model_dump_json()))
    return state
