"""Actual Dormant corruption changes existing resources and preserves its source debt."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import Followup, corrupt


class Corruption(Model):
    work: str = Field(min_length=1)
    actor: ActorRef
    gorgon: ActorRef
    event: str = Field(min_length=1)
    asset: str | None = None
    family: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=1200)


def inflict(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    gorgon: ActorRef,
    work: str,
    asset: str | None,
    description: str,
    event: str,
    *,
    piloting: bool,
) -> tuple[GameState, tuple[Followup, ...]]:
    """No resources are invented, repaired or transferred by taking actual Void."""
    if (
        actor.kind not in ("pilot", "external_pilot")
        or gorgon.kind != "gorgon"
        or not work.strip()
        or not event.strip()
        or any(
            x.get("kind") == "dormant_void_paid" and x.get("work") == work for x in original.facts
        )
    ):
        raise ValueError("Use the original affected role's unperformed Dormant corruption source")
    view = resolve(original, actor, bindings, require_current_profile=False)
    if not view.alive or view.piloting is not None and view.piloting != piloting:
        raise ValueError("Use the original living body's actual current cockpit context")
    source = (
        next((x for x in original.world.gorgons if x.id == gorgon.entity), None)
        if original.world
        else None
    )
    if source is None or source.gorgon_class != "dormant":
        raise ValueError("Recover the actual Dormant Gorgon's original source")
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_dive import _harpy_assets
        from girlframe.engine.m3_harpy_resources import assets

        if view.girl != "harpy":
            raise ValueError("Use this actual external role's supported Void resources")
        actual = assets(original, actor)
        selected = next((x for x in actual if x.id == asset and not x.void), None)
        if not description.strip():
            raise ValueError("Describe the actual Void alteration or already fully Void state")
        if asset is None:
            if any(not x.void for x in actual):
                raise ValueError("An actual uncorrupted Harpy Asset must take the gained Void")
            changed = GameState.model_validate_json(original.model_dump_json())
            family = "already_fully_void"
        else:
            if selected is None:
                raise ValueError("Choose the actual Harpy's uncorrupted Asset")
            changed = _harpy_assets(
                GameState.model_validate_json(original.model_dump_json()),
                actor,
                tuple(
                    x.model_copy(update={"void": True, "description": description})
                    if x.id == selected.id
                    else x
                    for x in actual
                ),
                event=event,
            )
            family = selected.family
        followups: tuple[Followup, ...] = ()
    else:
        sheet = original.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation or asset is None:
            raise ValueError("Choose the original Girl's actual uncorrupted Asset")
        result = corrupt(sheet, asset, description, piloting=piloting)
        changed = GameState.model_validate_json(original.model_dump_json())
        changed.sheets[actor.entity] = result.sheet
        selected_pilot = next(x for x in result.sheet.assets if x.id == asset)
        family, followups = selected_pilot.family, result.followups
    proof = Corruption(
        work=work,
        actor=actor,
        gorgon=gorgon,
        event=event,
        asset=asset,
        family=family,
        description=description,
    )
    changed.facts.append(
        dict(kind="dormant_void_paid", work=work, event=event, body=proof.model_dump_json())
    )
    return changed, followups
