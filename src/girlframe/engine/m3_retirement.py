"""Printed twenty-Permission Retirement pays before the actual career ending."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_intracadre_marriage import available, debit, payment_for
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
