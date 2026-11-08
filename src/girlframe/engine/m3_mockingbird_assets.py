"""Printed Call changes classification at the actual sole Asset origin, with real cap choices."""

from collections.abc import Mapping
from typing import Literal

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_assets import counts_toward_limit
from girlframe.engine.m3_core import Followup
from girlframe.engine.m3_dive import resources
from girlframe.engine.m3_harpy_resources import HarpyResource
from girlframe.engine.m3_mockingbird import CALL, owns


def classify(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    selection: Mapping[str, Literal["girl", "frame"]],
    replaced: tuple[str, ...],
    *,
    action: str,
    step: int,
    event: str,
    account: str,
) -> tuple[GameState, tuple[Followup, ...]]:
    if (
        not owns(original, actor, CALL)
        or not action
        or not event
        or not account.strip()
        or len(account) > 1200
        or step < 0
        or len(set(replaced)) != len(replaced)
        or any(
            x.get("kind") == "mockingbird_classification"
            and x.get("action") == action
            and x.get("step") == str(step)
            for x in original.facts
        )
    ):
        raise ValueError("Use the actual original owned Call option and its new source step")
    actual, _ = resources(original, actor)
    from girlframe.engine.m3_janus_storage import effective_assets
    from girlframe.engine.m3_janus_storage import ids as stored_ids

    effective = actual
    stored = stored_ids(original, actor)
    if actor.kind == "pilot":
        actual = tuple(original.sheets[actor.entity].assets)
    current = {x.id: x for x in actual}
    if (
        not set(selection) <= set(current)
        or set(selection) & set(replaced)
        or not set(replaced) <= set(current)
        or any(current[k].family == family for k, family in selection.items())
    ):
        raise ValueError("Choose actual owned Assets to move to their other printed family")
    resolve(original, actor, bindings, require_current_profile=False)
    proposed: dict[str, HarpyResource] = {}
    for old in actual:
        if old.id in selection:
            value = old.model_copy(
                update={"family": selection[old.id], "classification_event": event}
            )
            proposed[old.id] = type(old).model_validate_json(value.model_dump_json())
        else:
            proposed[old.id] = old

    def count(value: HarpyResource) -> bool:
        if actor.kind == "pilot":
            return counts_toward_limit(
                original.sheets[actor.entity],
                AssetState.model_validate_json(value.model_dump_json()),
            )
        # A retained intrinsic remains additional only in its original actual Frame.
        if value.family == "frame" and getattr(value, "intrinsic", None) == "wyvern_enormous":
            from girlframe.engine.m3_harpy_defeat import harpy
            from girlframe.engine.m3_void_state import HarpyState

            body = harpy(original, actor)
            if isinstance(body, HarpyState):
                archive = next(
                    (x for x in original.career_archives if x.id == body.original_archive), None
                )
                if archive:
                    from girlframe.engine.m2 import PilotSheet

                    oldsheet = PilotSheet.model_validate_json(archive.sheet_json)
                    if any(
                        x.actor == body.origin
                        and x.resulting_actor == actor
                        and x.frame_instance == body.frame_instance
                        and x.response_event == body.source_event
                        for x in original.void_thresholds
                    ) and not counts_toward_limit(
                        oldsheet, AssetState.model_validate_json(value.model_dump_json())
                    ):
                        return False
        return True

    overflow = {
        family: max(0, sum(x.family == family and count(x) for x in proposed.values()) - cap)
        for family, cap in (("girl", 4), ("frame", 5))
    }
    for family in ("girl", "frame"):
        removals = [current[x] for x in replaced if proposed[x].family == family]
        if len(removals) != overflow[family] or any(
            x.void or x.id in stored or not count(proposed[x.id]) for x in removals
        ):
            raise ValueError(
                "At each printed cap, replace exactly the excess non-Void ordinary Assets"
            )
    state = GameState.model_validate_json(original.model_dump_json())
    if actor.kind == "pilot":
        sheet = state.sheets[actor.entity]
        sheet.assets = [
            AssetState.model_validate_json(proposed[x.id].model_dump_json())
            for x in sheet.assets
            if x.id not in replaced
        ]
        sheet.revision += 1
    else:
        from girlframe.engine.m3_harpy_defeat import harpy, update
        from girlframe.engine.m3_void_state import HarpyState

        body = harpy(state, actor)
        if isinstance(body, HarpyState):
            state = update(
                state,
                actor,
                assets=tuple(proposed[x.id] for x in body.assets if x.id not in replaced),
            )
        else:
            assert state.world is not None
            state.world = state.world.model_copy(
                update={
                    "pilots": tuple(
                        row.model_copy(
                            update={
                                "assets": tuple(
                                    proposed[x.id] for x in row.assets if x.id not in replaced
                                )
                            }
                        )
                        if row.id == actor.entity
                        else row
                        for row in state.world.pilots
                    )
                }
            )
    # Item records retain object and source history. A cap-replaced ability loses only its
    # active mechanical binding; no old Asset is copied back into the character body.
    from girlframe.engine.m3_items import actual_asset, same_holder

    items = []
    for item in state.held_items:
        held_asset = (
            actual_asset(original, item) if same_holder(original, item.holder, actor) else None
        )
        if held_asset is not None and held_asset.id in replaced:
            item = item.model_copy(
                update={"asset_id": None, "asset_owner": None, "state_event": event}
            )
        elif held_asset is not None and held_asset.id in selection:
            item = item.model_copy(
                update={
                    "asset_json": proposed[held_asset.id].model_dump_json(),
                    "state_event": event,
                }
            )
        items.append(item)
    state.held_items = items
    state.facts.append(
        dict(
            kind="mockingbird_classification",
            action=action,
            step=str(step),
            event=event,
            actor=actor.model_dump_json(),
            before="|".join(current),
            moved="|".join(selection),
            removed="|".join(replaced),
            account=account,
        )
    )
    followups = []
    if actor.kind == "pilot":
        from girlframe.engine.m3_girl_runtime_state import has_rule

        sheet = state.sheets[actor.entity]
        bird = has_rule(sheet, "girl.mockingbird.risk-factor", "MOCKINGBIRD")
        for family in ("girl", "frame"):
            before = [x for x in effective if x.family == family]
            after = [x for x in effective_assets(state, actor) if x.family == family]
            became = bool(
                after
                and all(x.void for x in after)
                and not (before and all(x.void for x in before))
            )
            if became and (not bird or family == "frame"):
                followups.append(
                    Followup(
                        kind="mockingbird_resist"
                        if bird
                        else "girl_void_threshold"
                        if family == "girl"
                        else "frame_void_threshold",
                        owner=sheet.owner,
                        source_pdf=35 if bird else 19,
                    )
                )
    return state, tuple(followups)
