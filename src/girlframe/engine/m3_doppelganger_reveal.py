"""One original NPC Bond is exposed as the same person in Gorgon form."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, depth, migrate_actor, rebind, set_depth
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world import update, validate_initial_gorgon
from girlframe.engine.m3_world_state import Gorgon, Npc

RULE = "strain.void.high.1.2"
KIND = "strain_doppelganger_revealed"


class Reveal(Model):
    id: str
    source: str
    mask: Npc
    gorgon_class: Literal["benevolent", "erratic"]
    recipients: tuple[ActorRef, ...]
    account: str


def reveals(state: GameState) -> tuple[Reveal, ...]:
    return tuple(
        Reveal.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def original_bonds(state: GameState, npc: Npc) -> tuple[ActorRef, ...]:
    source = ActorRef(kind="npc", entity=npc.id)
    people = tuple(current_ref(state, uid) for uid in state.order)
    handler = active_handler(state)
    if handler is not None:
        people += (handler,)
    return tuple(x for x in people if depth(state, source, x) > 0)


def reveal(
    state: GameState,
    identity: str,
    source: str,
    npc_id: str | None,
    gorgon: Gorgon,
    account: str,
) -> GameState:
    world = state.world
    npc = next((x for x in world.npcs if x.id == npc_id), None) if world else None
    if (
        world is None
        or npc is None
        or not npc.alive
        or npc.controller != state.handler
        or "director" in npc.jobs
    ):
        raise ValueError(
            "Choose the original living NPC Bond under Handler control. Use the ordinary "
            "accepted role transfer first if someone else controls that NPC."
        )
    actor = ActorRef(kind="npc", entity=npc.id)
    new = ActorRef(kind="gorgon", entity=npc.id)
    view = resolve(state, actor, ())
    if (
        view.cell is None
        or view.custody
        or npc.captive_of is not None
        or any(x.open and any(r.actor == actor for r in x.roles) for x in state.scene_casts)
        or any(x.state == "pending" and x.npc.id == npc.id for x in world.npc_role_offers)
        or any(x.holder == actor for x in state.held_items)
    ):
        raise ValueError(
            "Resolve the original person's active cast, custody, handoff or held-item work "
            "before revealing their form."
        )
    audience = original_bonds(state, npc)
    if not audience or any(x.id == identity for x in reveals(state)):
        raise ValueError("Reveal one original Bond of the current Cadre or Handler")
    if (
        gorgon.id != npc.id
        or gorgon.name != npc.name
        or gorgon.cell != view.cell
        or gorgon.types != ("doppleganger",)
        or gorgon.gorgon_class not in ("benevolent", "erratic")
        or gorgon.tags
        or gorgon.position_event
        or gorgon.mask_source
    ):
        raise ValueError("Use the original identity and square with its printed Class and Type")
    validate_initial_gorgon(gorgon)

    # Migrate the legacy bonds stored on the disguise before removing it. Leave
    # ended bodies and ambiguous legacy references to normal source recovery.
    for key, bond_depth in npc.bonds.items():
        kind, entity = key.split(":", 1)
        other = (
            current_ref(state, int(entity))
            if kind in ("pilot", "handler")
            else ActorRef.model_validate(dict(kind=kind, entity=entity))
        )
        if other.kind != kind:
            raise ValueError("Recover the original role for the disguise's legacy Bond")
        actual: Literal[1, 2] = bond_depth
        state = set_depth(state, actor, other, actual, source)
    state = migrate_actor(state, actor, source)
    assert state.world is not None
    gorgon = gorgon.model_copy(update=dict(tags=npc.tags, mask_source=source))
    state.world = update(
        state.world,
        npcs=tuple(x for x in state.world.npcs if x.id != npc.id),
        gorgons=state.world.gorgons + (gorgon,),
    )
    changed = rebind(state, actor, new, source)
    handler = active_handler(changed)
    recipients = tuple(dict.fromkeys(audience + ((handler,) if handler else ())))
    record = Reveal(
        id=identity,
        source=source,
        mask=npc,
        gorgon_class="benevolent" if gorgon.gorgon_class == "benevolent" else "erratic",
        recipients=recipients,
        account=account,
    )
    changed.facts.append(dict(kind=KIND, id=identity, body=record.model_dump_json()))
    return changed
