"""Printed Handler starting effects; private drafts never authorize canon by themselves."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth, migrate_actor, rebind, set_depth
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_state import (
    GEAR,
    HISTORY_LABELS,
    PLAYBOOKS,
    TRAINER_PHRASES,
    Agreement,
    Conditioning,
    Draft,
    GearDetail,
    HandlerPersona,
    NpcAgreement,
    NpcStarting,
    SavedDraft,
    StartingBond,
)
from girlframe.engine.m3_world_state import WorldTag

__all__ = [
    "GEAR",
    "HISTORY_LABELS",
    "PLAYBOOKS",
    "Agreement",
    "Draft",
    "GearDetail",
    "HandlerPersona",
    "SavedDraft",
    "StartingBond",
    "agreement",
    "activate",
]


def generation(state: GameState) -> str:
    return state.handler_archives[-1].source_event if state.handler_archives else "initial"


def npc_agreement(saved: SavedDraft, owner: int, choice: NpcStarting) -> NpcAgreement:
    return NpcAgreement(
        persona_id=saved.persona_id,
        appointment=saved.appointment,
        handler=owner,
        name=saved.draft.name,
        relationship=choice,
        generation=saved.generation,
    )


def agreement(saved: SavedDraft, owner: int, choice: StartingBond) -> Agreement:
    phrases = (
        TRAINER_PHRASES[choice.prompt]
        if saved.draft.playbook == "Trainer" and choice.prompt is not None
        else ()
    )
    return Agreement(
        persona_id=saved.persona_id,
        appointment=saved.appointment,
        handler=owner,
        name=saved.draft.name,
        bond=choice,
        phrases=phrases,
        generation=saved.generation,
    )


def activate(
    original: GameState,
    owner: int,
    saved: SavedDraft,
    bindings: tuple[ProfileBinding, ...],
    accepted: tuple[Agreement, ...],
    event: str,
    *,
    npc_accepted: tuple[NpcAgreement, ...] = (),
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    if state.handler != owner or state.handler_persona is not None:
        raise ValueError("Activate only the original uncreated current Handler persona")
    if saved.generation != generation(state) or any(
        x.actor.incarnation == saved.persona_id for x in state.handler_archives
    ):
        raise ValueError("The original creation generation ended; start a fresh persona")
    initial = not state.handler_archives
    draft = saved.draft
    old_handler = ActorRef(kind="handler", entity=str(owner))
    if draft.missing:
        raise ValueError("Complete Handler creation: " + ", ".join(draft.missing))
    expected = tuple(agreement(saved, owner, x) for x in draft.starting)
    if sorted(x.model_dump_json() for x in accepted) != sorted(
        x.model_dump_json() for x in expected
    ):
        raise ValueError("Every original Girl must accept the exact current shared proposal")
    for choice in draft.starting:
        view = resolve(state, choice.pilot, bindings, require_current_profile=False)
        if view.rules != "girl_frame" or int(choice.pilot.entity) not in state.order:
            raise ValueError("Starting Bonds require actual current ranked Girls")
    if draft.playbook == "Insurgent":
        assert draft.sympathizer is not None
        wanted = set(draft.surveilled) | {draft.sympathizer}
        npcs = {x.id: x for x in state.world.npcs} if state.world else {}
        packages = {x.npc.entity: x for x in draft.npc_starting}
        expected_npcs = tuple(npc_agreement(saved, owner, x) for x in draft.npc_starting)
        if sorted(x.model_dump_json() for x in npc_accepted) != sorted(
            x.model_dump_json() for x in expected_npcs
        ):
            raise ValueError(
                "Each actual NPC controller must accept its exact starting relationship"
            )
        for identity in wanted:
            npc = npcs.get(identity)
            if npc is None or not npc.alive:
                raise ValueError("Choose actual living NPCs for the Insurgent's starting Bonds")
            package = packages.get(identity)
            if package is not None:
                if package.controller != npc.controller:
                    raise ValueError("Recover the actual NPC controller's source-bound response")
            elif (
                not initial or depth(state, old_handler, ActorRef(kind="npc", entity=identity)) < 1
            ):
                raise ValueError("Propose and obtain the actual NPC's new Personal starting Bond")
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    npc.model_copy(
                        update={
                            "tags": npc.tags
                            + tuple(
                                WorldTag(
                                    id=str(
                                        uuid5(
                                            NAMESPACE_URL,
                                            event + ":" + npc.id + ":" + label.lower(),
                                        )
                                    ),
                                    label=label,
                                    giver_entity="handler:" + saved.persona_id,
                                )
                                for label in ("Surveilled", "Sympathizer")
                                if (
                                    (label == "Surveilled" and npc.id in draft.surveilled)
                                    or (label == "Sympathizer" and npc.id == draft.sympathizer)
                                )
                                and not any(x.label == label for x in npc.tags)
                            )
                        }
                    )
                    for npc in state.world.npcs
                )
            }
        )
    order = list(state.order)
    for choice in draft.starting:
        uid = int(choice.pilot.entity)
        order.remove(uid)
        if choice.rank == "ace":
            order.insert(0, uid)
        else:
            order.append(uid)
    state.order = tuple(order)
    if initial:
        state = migrate_actor(state, old_handler, event)
    state.handler_persona = HandlerPersona(
        id=saved.persona_id,
        owner=owner,
        appointment=saved.appointment,
        draft=draft,
        source_event=event,
        conditioning=tuple(
            Conditioning(pilot=x.bond.pilot, phrases=x.phrases, source_event=event)
            for x in expected
            if x.phrases
        ),
        sticky_dogs=tuple(x.pilot for x in draft.starting if x.rank == "dog")
        if draft.playbook == "Dogrunner"
        else (),
    )
    actual = ActorRef(kind="handler", entity=str(owner), incarnation=saved.persona_id)
    if initial:
        state = rebind(state, old_handler, actual, event)
        state.scene_casts = [
            cast.model_copy(
                update={
                    "roles": tuple(
                        role.model_copy(update={"actor": actual, "source_event": event})
                        if role.actor == old_handler and role.controller == owner
                        else role
                        for role in cast.roles
                    ),
                    "revision": cast.revision + 1,
                }
            )
            if cast.open
            and any(role.actor == old_handler and role.controller == owner for role in cast.roles)
            else cast
            for cast in state.scene_casts
        ]
        for sheet in state.sheets.values():
            for tag in sheet.tags:
                if (
                    tag.giver == owner
                    and tag.giver_actor is None
                    and tag.giver_character is None
                    and tag.gm_setter_appointment is None
                ):
                    tag.giver_actor = actual
    for package in draft.npc_starting:
        state = set_depth(
            state, actual, package.npc, 2 if depth(state, actual, package.npc) == 2 else 1, event
        )
    for choice in draft.starting:
        value: Literal[1, 2] = (
            2 if depth(state, actual, choice.pilot) == 2 or choice.depth == 2 else 1
        )
        state = set_depth(state, actual, choice.pilot, value, event)
    return state
