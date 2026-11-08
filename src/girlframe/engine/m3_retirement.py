"""Printed twenty-Permission Retirement pays before the actual career ending."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_intracadre_marriage import available, debit, payment_for
from girlframe.engine.m3_offered_requisition_state import require_request
from girlframe.engine.m3_requisition_state import RetirementReceipt


def pay(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    expected: str,
    account: str,
    identity: str,
    archive_id: str,
    event: str,
) -> GameState:
    require_request(original, actor)
    state = GameState.model_validate_json(original.model_dump_json())
    current = resolve(state, actor, bindings)
    if (
        current.rules != "girl_frame"
        or current.ref.kind != "pilot"
        or current.source_sha256 != expected
    ):
        raise ValueError(
            "STALE_RETIREMENT: confirm the actual original Girl and her available Permissions"
        )
    if any(x.id == identity or x.source_event == event for x in state.requisitions):
        raise ValueError("This actual Retirement purchase source is already recorded")
    sheet = state.sheets[actor.entity]
    if available(state, actor) < 20:
        raise ValueError("Retirement costs twenty available Permissions")
    receipt = RetirementReceipt(
        id=identity, actor=actor, archive_id=archive_id, account=account, source_event=event
    )
    debit(
        state,
        actor,
        20,
        event=event,
        source=identity,
        payment=payment_for(state, actor, "retirement", 20),
    )
    sheet.revision += 1
    state.requisitions.append(receipt)
    return state


def grant_offered(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    expected: str,
    account: str,
    identity: str,
    archive_id: str,
    event: str,
    offer: str,
) -> GameState:
    """Actual offered Retirement receives no fictitious Permission payment."""
    state = GameState.model_validate_json(original.model_dump_json())
    actual = resolve(state, actor, bindings)
    if (
        actual.ref.kind != "pilot"
        or actual.rules != "girl_frame"
        or actual.source_sha256 != expected
        or not offer
        or any(x.id == identity or x.source_event == event for x in state.requisitions)
    ):
        raise ValueError("Use the current original Girl and genuine source-funded Retirement")
    if any(x.active and actor in (x.traveler, x.supervisor) for x in state.escort_journeys):
        raise ValueError("Complete the actual supervised journey before Retirement")
    if any(x.held and actor in (x.actor, x.target) for x in state.enforcer_grasps):
        raise ValueError("End the actual grasp before voluntary Retirement")
    body = next((x for x in state.placements if x.actor == actor), None)
    if body is not None and (
        body.custody is not None or body.subsumed or not body.vitals_active or body.incapacitated
    ):
        raise ValueError("Resolve actual custody, extraction or medical care before Retirement")
    state.requisitions.append(
        RetirementReceipt(
            id=identity,
            actor=actor,
            price=0,
            source_offer=offer,
            archive_id=archive_id,
            account=account,
            source_event=event,
        )
    )
    state.sheets[actor.entity].revision += 1
    return state
