"""Printed Dive Deep changes actual resources; table answers are human service work."""

from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState, shift_status
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import Followup, corrupt
from girlframe.engine.m3_dive_state import Effect
from girlframe.engine.m3_physical import lock_cockpit
from girlframe.engine.m3_world_state import WorldTag

PLAY = "dive_deep"


class Outcome(Model):
    state: GameState
    followups: tuple[Followup, ...] = ()


def nearby(state: GameState, actor: ActorRef, cast_npcs: tuple[str, ...]) -> tuple[str, ...]:
    if state.world is None:
        return ()
    body = next((x for x in state.placements if x.actor == actor), None)
    cell = body.girl_cell if body else None
    return tuple(
        x.id
        for x in state.world.npcs
        if x.alive and (x.id in cast_npcs or cell is not None and x.cell == cell)
    )


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
    handler: ActorRef,
    cast_npcs: tuple[str, ...],
) -> Outcome:
    state = GameState.model_validate_json(original.model_dump_json())
    view = resolve(state, actor, bindings, require_current_profile=False)
    if actor.kind != "pilot" or view.rules != "girl_frame" or not event or not action:
        raise ValueError("Dive Deep requires the original Girl and actual source effect")
    if any(
        x.get("kind") == "dive_effect" and x.get("action") == action and x.get("step") == str(step)
        for x in state.facts
    ):
        raise ValueError("This actual Dive effect was already applied")
    sheet = state.sheets[actor.entity]
    required: tuple[Followup, ...] = ()
    default = Effect(account=effect.account)
    supplied = {
        k
        for k in type(effect).model_fields
        if k != "account" and getattr(effect, k) != getattr(default, k)
    }
    allowed = {
        "void_and_unmark_all": {"asset", "description"},
        "erase_identity_and_table_question": {"identity", "question"},
        "nearby_npcs_gain_void": {"npcs"},
        "table_replaces_identity": {"identity", "replacement"},
        "locked_cockpit_extraction_requires_frame_consent": set(),
    }.get(option)
    if allowed is None or supplied - allowed:
        raise ValueError("Supply only this chosen printed Dive effect's actual details")
    if option == "void_and_unmark_all":
        if effect.asset is None:
            raise ValueError("Choose an actual uncorrupted Asset")
        own_frame = (
            view.inside_frame is True and view.occupied_frame_instance == view.frame_instance
        )
        context = own_frame if view.inside_frame is not None else piloting
        result = corrupt(sheet, effect.asset, effect.description, piloting=context)
        sheet = result.sheet
        for entry in sheet.identities:
            if entry.id not in sheet.sedation_locked:
                entry.marked = False
        state.sheets[actor.entity] = sheet
        required = result.followups
    elif option in ("erase_identity_and_table_question", "table_replaces_identity"):
        identity = next(
            (x for x in sheet.identities if x.id == effect.identity and not x.protected), None
        )
        if identity is None:
            raise ValueError("Choose one current ordinary unprotected Identity")
        if option == "erase_identity_and_table_question":
            if not effect.question.strip():
                raise ValueError("Ask the actual question for the table")
            sheet.identities.remove(identity)
        else:
            if not effect.replacement.strip():
                raise ValueError("The table must agree on an actual new Identity")
            identity.name = effect.replacement.strip()
            if identity.id in sheet.sedation_locked:
                identity.marked = True
        sheet.revision += 1
    elif option == "nearby_npcs_gain_void":
        expected = nearby(state, actor, cast_npcs)
        if not expected or {x.npc for x in effect.npcs} != set(expected):
            raise ValueError(
                "Apply one Handler-owned manifestation to every actual nearby living NPC"
            )
        if handler.kind != "handler" or int(handler.entity) != state.handler:
            raise ValueError("The actual current Handler chooses NPC Void manifestations")
        selected = {x.npc: x.manifestation for x in effect.npcs}
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
                                        label="Void of the " + selected[npc.id],
                                        giver_entity=handler.model_dump_json(),
                                    ),
                                )
                            }
                        )
                        if npc.id in selected
                        else npc
                        for npc in state.world.npcs
                    )
                }
            )
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
