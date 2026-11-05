"""One actual-role social Punishment port, with no fabricated NPC resource sheet."""

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import change, current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_punishments import KINDS, Details, validate
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import WorldTag

SOCIAL = ("quality_time", "reduced_socialization")


def bond_ref(state: GameState, actor: ActorRef) -> ActorRef:
    # A temporary Director-presence rules context is the same actual Handler persona.
    return current_ref(state, int(actor.entity)) if actor.kind == "handler" else actor


def view(state: GameState, actor: ActorRef, bindings: tuple[ProfileBinding, ...]) -> ActorView:
    if actor.kind == "handler" and actor == current_ref(state, int(actor.entity)):
        context = next(
            (x for x in state.director_contexts if x.active and x.handler == int(actor.entity)),
            None,
        )
        if context is not None:
            return resolve(
                state,
                ActorRef(kind="handler", entity=actor.entity, incarnation=context.id),
                bindings,
                require_current_profile=False,
            )
    return resolve(state, actor, bindings, require_current_profile=False)


def available(
    state: GameState, subject: ActorRef, executor: ActorRef, bindings: tuple[ProfileBinding, ...]
) -> tuple[str, ...]:
    target = view(state, subject, bindings)
    resolve(state, executor, bindings, require_current_profile=False)
    if subject == executor or executor.kind != "pilot":
        return ()
    if subject.kind == "pilot" and target.rules == "girl_frame":
        # Severe effects require the actual Handler to inflict them. Passing Responsibility
        # changes selection ownership; it cannot satisfy this mandatory execution.
        return tuple(
            k
            for k, (_, severity) in KINDS.items()
            if severity != "severe" and k not in ("passing_responsibility", "lobotomization")
        )
    if subject.kind in ("npc", "handler"):
        return SOCIAL
    return ()


def social(
    original: GameState,
    subject: ActorRef,
    executor: ActorRef,
    instruction: Instruction,
    bindings: tuple[ProfileBinding, ...],
    event: str,
    identity: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    target = view(state, subject, bindings)
    acting = resolve(state, executor, bindings, require_current_profile=False)
    details = Details.model_validate_json(instruction.details_json)
    validate(details)
    if instruction.kind not in SOCIAL or details.kind != instruction.kind:
        raise ValueError("Use a source-supported actual-role social Punishment")
    if instruction.kind == "quality_time":
        if not details.tag.strip() or instruction.counterpart is not None:
            raise ValueError(
                "Quality Time gives its actual chosen Tag and deepens the executor Bond"
            )
        state = change(state, bond_ref(state, subject), bond_ref(state, executor), 1, event)
        if subject.kind == "npc" and state.world is not None:
            npc = next(x for x in state.world.npcs if x.id == subject.entity)
            tagged = npc.model_copy(
                update={
                    "tags": (
                        *npc.tags,
                        WorldTag(
                            id=identity,
                            label=details.tag.strip(),
                            giver_entity=executor.model_dump_json(),
                        ),
                    )
                }
            )
            state.world = state.world.model_copy(
                update={"npcs": tuple(tagged if x.id == npc.id else x for x in state.world.npcs)}
            )
        else:
            tag = TagState(
                id=identity,
                label=details.tag.strip(),
                giver=acting.controller,
                giver_actor=executor,
                observers=(acting.controller, target.controller),
            )
            if subject.kind == "handler":
                state.handler_tags.append(tag)
            elif subject.kind == "pilot":
                state.sheets[subject.entity].tags.append(tag)
            else:
                raise ValueError("This actual role's Tag resource is unavailable")
    else:
        peer = instruction.counterpart
        if (
            peer is None
            or peer == subject
            or depth(state, bond_ref(state, subject), bond_ref(state, peer)) < 1
        ):
            raise ValueError("Choose an actual current Bond counterpart to weaken")
        resolve(state, peer, bindings, require_current_profile=False)
        state = change(state, bond_ref(state, subject), bond_ref(state, peer), -1, event)
    return state
