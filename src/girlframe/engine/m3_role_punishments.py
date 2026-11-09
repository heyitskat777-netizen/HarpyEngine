"""One actual-role social Punishment port, with no fabricated NPC resource sheet."""

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import change, depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_punishments import KINDS, Details, validate
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import WorldTag

SOCIAL = ("quality_time", "reduced_socialization")


def bond_ref(state: GameState, actor: ActorRef) -> ActorRef:
    # A temporary Director-presence rules context is the same actual Handler persona.
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import body_original

        return body_original(state, actor).actor
    return actor


def view(state: GameState, actor: ActorRef, bindings: tuple[ProfileBinding, ...]) -> ActorView:
    from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body

    if actor.kind == "handler" and actor == active_handler(state):
        context = next(
            (
                x
                for x in state.director_contexts
                if x.active
                and x.handler == int(actor.entity)
                and same_handler_body(
                    state, ActorRef(kind="handler", entity=actor.entity, incarnation=x.id)
                )
            ),
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
    view(state, executor, bindings)
    harpy_executor = (
        executor.kind == "external_pilot" and view(state, executor, bindings).girl == "harpy"
    )
    if (
        subject == executor
        or executor.kind not in ("pilot", "npc", "handler")
        and not harpy_executor
    ):
        return ()
    if subject.kind == "pilot" and target.rules == "girl_frame":
        if executor.kind == "npc" or harpy_executor:
            return ("reduced_socialization",) if depth(state, subject, executor) == 2 else SOCIAL
        # Severe effects require the actual Handler to inflict them. Passing Responsibility
        # changes selection ownership; it cannot satisfy this mandatory execution.
        return tuple(
            k
            for k, (_, severity) in KINDS.items()
            if (severity != "severe" or executor.kind == "handler")
            and k not in ("passing_responsibility", "lobotomization")
        )
    if subject.kind in ("npc", "handler", "external_pilot", "gorgon"):
        kinds = list(SOCIAL)
        if not any(
            subject in (x.first, x.second) and x.depth > 0 for x in state.actor_bonds
        ) and not any(
            state.world is not None and x.id == subject.entity and any(x.bonds.values())
            for x in (state.world.npcs if state.world else ())
        ):
            # Existing numeric PC/Handler Bonds are included by the source selector;
            # no empty Reduced Socialization option for a world actor with no Bond.
            if subject.kind in ("external_pilot", "gorgon"):
                kinds.remove("reduced_socialization")
        return tuple(kinds)
    return ()


def social(
    original: GameState,
    subject: ActorRef,
    executor: ActorRef,
    instruction: Instruction,
    bindings: tuple[ProfileBinding, ...],
    event: str,
    identity: str,
    *,
    source_kind: str | None = None,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    target = view(state, subject, bindings)
    acting = view(state, executor, bindings)
    details = Details.model_validate_json(instruction.details_json)
    validate(details)
    if (
        source_kind in ("compliance_virus", "janus_training")
        and subject.kind == "external_pilot"
        and target.girl == "harpy"
        and instruction.kind == "stimulant_injection"
    ):
        from girlframe.engine.m3_harpy_defeat import harpy, update

        if details.kind != instruction.kind or instruction.counterpart is not None:
            raise ValueError("Use the actual printed Stimulant Injection without unrelated choices")
        from girlframe.engine.m3_leviathan_obsession import allowed_gain

        body = harpy(state, subject)
        return update(
            state,
            subject,
            heat=body.heat + allowed_gain(state, subject, 7, "Stimulant Injection", event),
        )
    self_virus = subject == executor and source_kind == "compliance_virus"
    # A source-authenticated self-purge can weaken a real OTHER Bond; no self-Bond.
    applicable = (
        ("reduced_socialization",) if self_virus else available(state, subject, executor, bindings)
    )
    if instruction.kind not in applicable:
        raise ValueError("This target needs actual resources for every printed Punishment effect")
    if subject.kind == "pilot":
        from girlframe.engine.m3_girl_runtime_state import has_rule
        from girlframe.engine.m3_learned_play_state import active_hound_status, clear_hound_status

        if (
            has_rule(state.sheets[subject.entity], "girl.alpha.nothing-more-than-a-hound", "ALPHA")
            or active_hound_status(state, subject) is not None
        ):
            clear_hound_status(state, subject, "punishment", event)
            state.sheets[subject.entity].status_marked = False
    if instruction.kind not in SOCIAL or details.kind != instruction.kind:
        raise ValueError("Use a source-supported actual-role social Punishment")
    if instruction.kind == "quality_time":
        if not details.tag.strip() or instruction.counterpart is not None:
            raise ValueError(
                "Quality Time gives its actual chosen Tag and deepens the executor Bond"
            )
        state = change(state, bond_ref(state, subject), bond_ref(state, executor), 1, event)
        from girlframe.engine.m3_janus import find as core_body

        if core_body(state, subject) is not None:
            from girlframe.engine.m3_harpy_defeat import give_tag

            return give_tag(
                state,
                subject,
                executor,
                details.tag.strip(),
                event,
                identity,
                tuple(sorted({acting.controller, target.controller})),
            )
        if (
            subject.kind in ("npc", "gorgon", "external_pilot")
            and state.world is not None
            and not any(x.id == subject.entity for x in state.harpy_states)
        ):
            collection = {"npc": "npcs", "gorgon": "gorgons", "external_pilot": "pilots"}[
                subject.kind
            ]
            rows = getattr(state.world, collection)
            npc = next(x for x in rows if x.id == subject.entity)
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
                update={collection: tuple(tagged if x.id == npc.id else x for x in rows)}
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
            elif subject.kind == "external_pilot":
                from girlframe.engine.m3_void_state import HarpyTag

                actual = HarpyTag(
                    id=identity,
                    label=details.tag.strip(),
                    giver=acting.controller,
                    giver_ref=executor,
                    observers=(acting.controller, target.controller),
                )
                state.harpy_states = [
                    x.model_copy(update={"tags": (*x.tags, actual)})
                    if x.id == subject.entity
                    else x
                    for x in state.harpy_states
                ]
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
