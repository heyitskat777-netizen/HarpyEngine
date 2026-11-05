"""Finite Handler Play grants; a printed counter never changes campaign GM authority."""

from girlframe.engine.m2 import GameState, TagState, shift_status
from girlframe.engine.m3_handler_play_state import Effect, HandlerPlay, Play
from girlframe.engine.m3_void_state import HarpyTag
from girlframe.engine.m3_world import introduce_npc
from girlframe.engine.m3_world_state import WorldTag


def record(state: GameState, identity: str) -> HandlerPlay:
    item = next((x for x in state.handler_plays if x.id == identity), None)
    if item is None:
        raise ValueError("This original owned Handler Play is unavailable")
    return item


def replace(state: GameState, value: HandlerPlay) -> None:
    state.handler_plays = [value if x.id == value.id else x for x in state.handler_plays]


def select(state: GameState, identity: str, play: Play, effect: Effect, event: str) -> GameState:
    changed = GameState.model_validate_json(state.model_dump_json())
    grant = record(changed, identity)
    expected = "mess" if effect.kind in ("status", "tag", "damage") else effect.kind
    if grant.state != "pending" or play != expected or not event.strip():
        raise ValueError("Use this actual pending Handler Play and its matching effect")
    if grant.nonbody_only and effect.kind not in ("brief", "escalate", "support", "expectation"):
        raise ValueError(
            "The actual original ended; only the source-owned nonbody procedure remains"
        )
    if effect.target is not None and effect.target not in grant.targets:
        raise ValueError("This grant cannot affect another original character")
    replace(
        changed,
        grant.model_copy(
            update=dict(selected=play, effect=effect, effect_event=event, state="awaiting_effect")
        ),
    )
    return changed


def direct(state: GameState, identity: str, event: str) -> GameState:
    changed = GameState.model_validate_json(state.model_dump_json())
    grant = record(changed, identity)
    effect = grant.effect
    if grant.state != "awaiting_effect" or effect is None or grant.effect_event != event:
        raise ValueError("Apply only the actual committed owned effect")
    if effect.kind == "status":
        target = effect.target
        if target is None or target.kind != "pilot":
            raise ValueError("Status requires an actual original Girl with a Cadre position")
        sheet = changed.sheets.get(target.entity)
        if sheet is None or sheet.character_id != target.incarnation:
            raise ValueError("The original target ended; replacements cannot inherit this effect")
        shift_status(changed, sheet.owner, effect.status)
    elif effect.kind == "tag":
        target = effect.target
        assert target is not None
        tag = TagState(
            id=identity + ":tag",
            label=effect.tag,
            giver=grant.chooser_controller,
            observers=tuple(
                dict.fromkeys((grant.chooser_controller, *grant.target_controllers.values()))
            ),
            giver_actor=grant.chooser_actor,
            gm_setter_appointment=grant.appointment if grant.chooser_actor is None else None,
            gm_setter_grant=grant.id if grant.adjudicator_ref is not None else None,
        )
        if target.kind == "pilot":
            sheet = changed.sheets.get(target.entity)
            if sheet is None or sheet.character_id != target.incarnation:
                raise ValueError(
                    "The original target ended; replacements cannot inherit this effect"
                )
            sheet.tags.append(tag)
            sheet.revision += 1
        elif target.kind == "handler":
            from girlframe.engine.m3_handler_consequences import same_handler_body

            if not same_handler_body(changed, target):
                raise ValueError("Use the actual living original Handler body")
            changed.handler_tags.append(tag)
        elif target.kind == "npc" and changed.world:
            npc = next((x for x in changed.world.npcs if x.id == target.entity and x.alive), None)
            if npc is None:
                raise ValueError("Use the actual living NPC")
            tagged = npc.model_copy(
                update={
                    "tags": (
                        *npc.tags,
                        WorldTag(
                            id=tag.id,
                            label=tag.label,
                            giver_entity=grant.chooser_actor.model_dump_json()
                            if grant.chooser_actor
                            else "ooc-gm:"
                            + str(grant.chooser_controller)
                            + ":"
                            + str(grant.appointment),
                        ),
                    )
                }
            )
            changed.world = changed.world.model_copy(
                update={"npcs": tuple(tagged if x.id == npc.id else x for x in changed.world.npcs)}
            )
        elif target.kind == "external_pilot" and (
            any(x.id == target.entity and x.alive for x in changed.harpy_states)
            or any(x.id == target.entity for x in changed.native_harpies)
        ):
            from girlframe.engine.m3_harpy_defeat import harpy, update

            body = harpy(changed, target)
            assigned = HarpyTag(
                id=tag.id,
                label=tag.label,
                giver=tag.giver,
                giver_ref=tag.giver_actor,
                gm_setter_appointment=tag.gm_setter_appointment,
                gm_setter_event=event if tag.gm_setter_appointment else None,
                gm_setter_grant=tag.gm_setter_grant,
                observers=tag.observers,
            )
            changed = update(changed, target, tags=(*body.tags, assigned))
        else:
            raise ValueError("This actual target has no canonical Tag resource port")
    elif effect.kind == "support":
        npc = effect.npc
        if changed.world is None or npc is None:
            raise ValueError("Use the actual initialized world and new employee")
        if (
            npc.controller != grant.chooser_controller
            or not npc.revealed
            or npc.tags
            or npc.bonds
            or npc.captive_of is not None
            or npc.custody_event is not None
            or not npc.alive
            or not set(npc.jobs)
            <= {
                "base_personnel",
                "mechanic",
                "guard",
                "intelligence_agent",
                "public_relations",
                "scientist",
                "doctor",
            }
            or npc.secret_factions
        ):
            raise ValueError(
                "Introduce a real revealed employee under your own control without "
                "invented resources/custody"
            )
        changed.world = introduce_npc(changed.world, npc)
    elif effect.kind not in ("brief", "escalate", "expectation"):
        raise ValueError("This effect requires its actual specialized runtime port")
    return changed


def complete(state: GameState, identity: str, event: str) -> GameState:
    changed = GameState.model_validate_json(state.model_dump_json())
    grant = record(changed, identity)
    if grant.state != "awaiting_effect" or not event.strip():
        raise ValueError("Finish only the actual effect after all required consequences")
    replace(changed, grant.model_copy(update=dict(state="complete", completed_event=event)))
    return changed
