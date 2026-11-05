"""No dice, restoration or favorable automatic result is invented for forbidden rolls."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_adjudication_state import Decision, Required
from girlframe.engine.m3_lobotomy import blocked_play


def validate(state: GameState, required: Required) -> None:
    if required.play == "harpy_defeat":
        from girlframe.engine.m3_harpy_defeat import harpy
        from girlframe.engine.m3_void_state import HarpyState

        body = harpy(state, required.actor)
        prohibition = next(
            (x for x in body.blocked_plays if x.play in ("defeat", "harpy_defeat")), None
        )
        surgery = next(
            (
                x
                for x in state.lobotomies
                if prohibition is not None and x.id == prohibition.surgery
            ),
            None,
        )
        if (
            not isinstance(body, HarpyState)
            or body.controller != required.patient_controller
            or (required.adjudicator is None and state.handler != required.controller)
            or prohibition != required.prohibition
            or surgery is None
            or surgery.phase != "applied"
            or surgery.subject != body.origin
            or surgery.applied_event != prohibition.source_event
            or surgery.plan is None
            or surgery.plan.forbidden_play != "defeat"
        ):
            raise ValueError("Recover the actual Harpy's inherited original surgery prohibition")
        return
    if (
        current_ref(state, int(required.actor.entity)) != required.actor
        or state.handler != required.controller
    ):
        raise ValueError("Recover the actual original Girl and source-appointed Handler")
    sheet = state.sheets[required.actor.entity]
    prohibition = blocked_play(sheet, required.play)
    surgery = next(
        (x for x in state.lobotomies if prohibition is not None and x.id == prohibition.surgery),
        None,
    )
    if (
        prohibition != required.prohibition
        or surgery is None
        or surgery.phase != "applied"
        or surgery.subject != required.actor
        or surgery.applied_event != prohibition.source_event
        or surgery.plan is None
        or surgery.plan.forbidden_play != required.play
    ):
        raise ValueError("A mandatory exception needs its actual completed surgery prohibition")


def receipt(decision: Decision, identity: str, timestamp: str) -> dict[str, object]:
    """The assigned integer is the whole pre-Tag total, with no hidden numeric modifier."""
    return dict(
        id=identity,
        action_id=decision.action,
        faces=None,
        heat=0,
        pre_total=decision.total,
        base_modifier=0,
        pre_modifiers=[],
        modifier_source="MANUAL ADJUDICATION",
        rng_source="manual_adjudication",
        rolled_utc=timestamp,
        adjudication=decision.model_dump(mode="json"),
    )
