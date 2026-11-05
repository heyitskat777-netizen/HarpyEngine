"""Owned standards belong to the actual Girl and rule, not a draft playbook label."""

from pydantic import Field

from girlframe.engine.creation_details import StandardChoice
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, StandardGrant

RULE = "girl.princess.to-a-higher-standard"


class Plan(Model):
    owner: ActorRef
    peer: ActorRef
    handler: ActorRef
    appointment: str = Field(min_length=1)
    own: StandardChoice
    source_work: str | None = None


def labels(sheet: object) -> list[dict[str, object]]:
    runtime = getattr(sheet, "girl_runtime", None)
    if runtime and runtime.standards:
        return [
            dict(role=x.role, label=x.choice.label, is_order=x.role == "handler")
            for x in runtime.standards
        ]
    review = getattr(sheet, "review", None)
    details = review.creation.girl_details if review else None
    result: list[dict[str, object]] = []
    if details and details.own_standard:
        result.append(dict(role="own", label=details.own_standard.label, is_order=False))
    if review:
        result.extend(
            dict(
                role="peer" if x.role == "princess_peer" else "handler",
                label=x.standard.label,
                is_order=x.role == "princess_handler",
            )
            for x in review.coordination
            if x.standard and x.role in ("princess_peer", "princess_handler")
        )
    return result


def ready(sheet: object) -> bool:
    choices = labels(sheet)
    return len(choices) == 3 and {x["role"] for x in choices} == {"own", "peer", "handler"}


def validate(state: GameState, plan: Plan, bindings: tuple[ProfileBinding, ...]) -> None:
    owner = resolve(state, plan.owner, bindings, require_current_profile=False)
    peer = resolve(state, plan.peer, bindings, require_current_profile=False)
    if (
        owner.rules != "girl_frame"
        or peer.rules != "girl_frame"
        or plan.owner == plan.peer
        or depth(state, plan.owner, plan.peer) < 1
        or plan.handler.kind != "handler"
        or plan.handler.entity != str(state.handler)
    ):
        raise ValueError(
            "Choose the actual Girl, a currently bonded other Girl and the current Handler"
        )


def grant(
    original: GameState,
    plan: Plan,
    selected: tuple[StandardGrant, ...],
    bindings: tuple[ProfileBinding, ...],
) -> GameState:
    validate(original, plan, bindings)
    if len(selected) != 3 or {x.role for x in selected} != {"own", "peer", "handler"}:
        raise ValueError("All three actual standard choosers must provide their own choice")
    expected = {"own": plan.owner, "peer": plan.peer, "handler": plan.handler}
    if any(x.chooser != expected[x.role] for x in selected):
        raise ValueError("Each standard belongs to its original chooser")
    if next(x for x in selected if x.role == "own").choice != plan.own:
        raise ValueError("Preserve the original Girl's actual chosen standard")
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets[plan.owner.entity]
    runtime = sheet.girl_runtime or GirlRuntime()
    sheet.girl_runtime = runtime.model_copy(update={"standards": selected})
    sheet.revision += 1
    return state
