"""Paid Sup grows one real already-Void Asset at an actual Void-gain source."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_class_grafts import held as class_held
from girlframe.engine.m3_core import Followup
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.priestess.sup-of-primordial-flesh"


class Growth(Model):
    name: str = Field(min_length=1, max_length=120)
    family: Literal["girl", "frame"]
    replace: str | None = None


class Grown(Model):
    actor: ActorRef
    frame: str
    purchase: str
    action: str
    step: int = Field(ge=0)
    event: str
    asset: str
    choice: Growth
    description: str = Field(min_length=1, max_length=1200)


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    return class_held(state, actor, RULE)


def growths(state: GameState) -> tuple[Grown, ...]:
    return tuple(
        Grown.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "sup_growth"
    )


def offers(state: GameState, actor: ActorRef) -> dict[str, object] | None:
    from girlframe.engine.m3_assets import can_replace_at_limit, counts_toward_limit, frame_capacity
    from girlframe.engine.m3_janus_storage import ids

    if held(state, actor) is None:
        return None
    sheet = state.sheets[actor.entity]
    stored = ids(state, actor)
    eligible = [x for x in sheet.assets if can_replace_at_limit(sheet, x) and x.id not in stored]
    families = [
        family
        for family, cap in (("girl", 4), ("frame", frame_capacity(sheet, state)))
        if sum(x.family == family and counts_toward_limit(sheet, x) for x in sheet.assets) < cap
        or any(x.family == family for x in eligible)
    ]
    return (
        dict(
            families=families,
            replacements=[dict(id=x.id, label=x.name, family=x.family) for x in eligible],
        )
        if families
        else None
    )


def grow(
    original: GameState,
    actor: ActorRef,
    choice: Growth,
    description: str,
    action: str,
    event: str,
    *,
    piloting: bool,
    step: int = 0,
) -> tuple[GameState, tuple[Followup, ...], Grown]:
    from girlframe.engine.m3_class_retention import binding
    from girlframe.engine.m3_core import install, void_followups
    from girlframe.engine.m3_janus_storage import ids

    receipt = held(original, actor)
    if (
        receipt is None
        or not action
        or not event
        or not choice.name.strip()
        or not description.strip()
        or len(description) > 1200
        or any(
            x.actor == actor and x.action == action and x.step == step and x.event == event
            for x in growths(original)
        )
    ):
        raise ValueError("Use this original Frame's paid Sup once for its actual owned Void gain")
    state = GameState.model_validate_json(original.model_dump_json())
    identity = str(uuid5(NAMESPACE_URL, f"girlframe:sup:{actor.token}:{action}:{step}:{event}"))
    asset = AssetState(
        id=identity,
        family=choice.family,
        name=choice.name.strip(),
        description=description,
        void=True,
    )
    result = install(
        state.sheets[actor.entity],
        asset,
        replace=choice.replace,
        effective_void=ids(state, actor),
        state=state,
    )
    state.sheets[actor.entity] = result.sheet
    fact = Grown(
        actor=actor,
        frame=binding(original, receipt)[0],
        purchase=receipt.id,
        action=action,
        step=step,
        event=event,
        asset=identity,
        choice=choice,
        description=description,
    )
    state.facts.append(dict(kind="sup_growth", id=identity, body=fact.model_dump_json()))
    return (
        state,
        void_followups(result.sheet, piloting=piloting, effective_void=ids(state, actor)),
        fact,
    )
