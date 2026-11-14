"""Printed intimacy effects change actual original resources and retain their sole origin."""

from collections.abc import Sequence
from typing import Literal

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_bonds import change, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import Followup
from girlframe.engine.m3_harpy_resources import HarpyResource
from girlframe.engine.m3_janus_storage import GainSource
from girlframe.engine.m3_mockingbird import SEX, give_tag, owns
from girlframe.engine.m3_mockingbird_state import Capability, Exposure, Starry
from girlframe.engine.m3_sup import Growth
from girlframe.engine.m3_world_state import AdversaryPilot, Gorgon


def assets(state: GameState, actor: ActorRef) -> tuple[HarpyResource, ...]:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("Recover the actual original counterpart's resources")
        from girlframe.engine.m3_janus_storage import effective_assets

        return effective_assets(state, actor)
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        try:
            harpy(state, actor)
        except ValueError:
            pass
        else:
            from girlframe.engine.m3_harpy_resources import assets as harpy_assets

            return harpy_assets(state, actor)
    from girlframe.engine.m3_items import mechanical_assets

    values: list[HarpyResource] = list(mechanical_assets(state, actor))
    if state.world:
        base: AdversaryPilot | Gorgon | None = None
        if actor.kind == "external_pilot":
            base = next((x for x in state.world.pilots if x.id == actor.entity), None)
        elif actor.kind == "gorgon":
            base = next((x for x in state.world.gorgons if x.id == actor.entity), None)
        if base is not None:
            values[:0] = list(base.assets)
    if len({x.id for x in values}) != len(values):
        raise ValueError("Recover the actual counterpart's unique mechanical Asset origins")
    return tuple(values)


def update_assets(
    original: GameState, actor: ActorRef, values: Sequence[HarpyResource], event: str
) -> GameState:
    old = assets(original, actor)
    proposed = {x.id: x for x in values}
    allowed = {"void", "description", "concealed"}
    if (
        not event
        or set(proposed) != {x.id for x in old}
        or len(proposed) != len(values)
        or any(
            type(x) is not type(proposed[x.id])
            or x.model_dump(exclude=allowed) != proposed[x.id].model_dump(exclude=allowed)
            for x in old
        )
    ):
        raise ValueError(
            "Change only actual corruption/concealment at every existing sole Asset origin"
        )
    for value in values:
        type(value).model_validate_json(value.model_dump_json())
    state = GameState.model_validate_json(original.model_dump_json())
    if actor.kind == "pilot":
        from girlframe.engine.m3_janus_storage import active, put

        stored = {x.asset: x for x in active(original, actor)}
        original_assets = state.sheets[actor.entity].assets
        output = []
        for raw in original_assets:
            value = AssetState.model_validate_json(proposed[raw.id].model_dump_json())
            if raw.id in stored:
                effective = next(x for x in old if x.id == raw.id)
                if value.void == effective.void and value.description == effective.description:
                    value.void, value.description = raw.void, raw.description
                elif not value.void:
                    put(state, stored[raw.id].model_copy(update={"removed_event": event}))
                else:
                    raise ValueError("Do not silently make a stored alteration permanent")
            output.append(value)
        state.sheets[actor.entity].assets = output
        state.sheets[actor.entity].revision += 1
        return state
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy, update
        from girlframe.engine.m3_void_state import HarpyState

        try:
            body = harpy(state, actor)
        except ValueError:
            body = None
        if isinstance(body, HarpyState):
            state = update(state, actor, assets=tuple(proposed[x.id] for x in body.assets))
        elif state.world is not None:
            state.world = state.world.model_copy(
                update={
                    "pilots": tuple(
                        row.model_copy(update={"assets": tuple(proposed[x.id] for x in row.assets)})
                        if row.id == actor.entity
                        else row
                        for row in state.world.pilots
                    )
                }
            )
    elif actor.kind == "gorgon":
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "gorgons": tuple(
                    row.model_copy(update={"assets": tuple(proposed[x.id] for x in row.assets)})
                    if row.id == actor.entity
                    else row
                    for row in state.world.gorgons
                )
            }
        )
    from girlframe.engine.m3_items import actual_asset, same_holder

    state.held_items = [
        item.model_copy(
            update={"asset_json": proposed[actual.id].model_dump_json(), "state_event": event}
        )
        if same_holder(original, item.holder, actor)
        and (actual := actual_asset(original, item)) is not None
        else item
        for item in state.held_items
    ]
    return state


def exposure(
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    kind: Literal["teaching", "both_risk", "low_tag"],
    action: str,
    event: str,
) -> GameState:
    value = Exposure(
        id="mock-exposure:" + action + ":" + kind,
        source_action=action,
        actor=actor,
        counterpart=target,
        kind=kind,
        source_event=event,
    )
    state.mockingbird = state.mockingbird.model_copy(
        update={"exposures": (*state.mockingbird.exposures, value)}
    )
    return state


def _owns_source(state: GameState, actor: ActorRef, action: str) -> bool:
    """Pure effect admission; the service proves canonical source/receipt first."""
    if owns(state, actor, SEX):
        return True
    from girlframe.engine.m3_learned_play_state import learned_sex_links, sex_party_refs

    trigger = next((x for x in state.mockingbird.triggers if x.action == action), None)
    if trigger is not None and trigger.bonded_source is not None:
        from girlframe.engine import m3_bonded as bonded

        parent = next(
            (x for x in bonded.records(state, bonded.Source) if x.id == trigger.bonded_source), None
        )
        from girlframe.engine.m3_girl_runtime_state import has_rule

        native = bool(
            parent is not None
            and parent.learned_source is None
            and actor.kind == "pilot"
            and actor.entity in state.sheets
            and has_rule(state.sheets[actor.entity], bonded.SEX, "BONDED")
            and parent.pair.kind == "pilot"
            and parent.pair.entity in state.sheets
            and has_rule(state.sheets[parent.pair.entity], SEX, "MOCKINGBIRD")
        )
        return bool(
            parent is not None
            and parent.route == "delegated"
            and parent.delegated_rule == SEX
            and parent.phase in ("bound", "complete")
            and parent.actor == actor
            and trigger.play == "mockingbird_sex"
            and trigger.actor == actor
            and trigger.learned_source is None
            and trigger.learned_sex_source is None
            and trigger.changeling_source is None
            and bool(trigger.parties)
            and len({x.actor for x in trigger.parties}) == len(trigger.parties)
            and trigger.parties[0].actor == parent.target
            and all(
                x.actor != actor
                and x.decision == "accepted"
                and x.event is not None
                and any(
                    r.actor == x.actor and r.controller == x.controller for r in parent.cast.roles
                )
                for x in trigger.parties
            )
            and any(
                x.source == parent.id
                and x.session == trigger.id
                and x.rule == SEX
                and x.actor == actor
                and x.target == parent.target
                for x in bonded.records(state, bonded.Delegation)
            )
            and (
                native
                or any(
                    x.id == parent.learned_source
                    and x.rule_id == bonded.SEX
                    and x.session == parent.id
                    and x.actor == actor
                    and x.target == parent.target
                    and x.action == action
                    and x.accepted is True
                    and x.bound_event is not None
                    and x.roll_event is not None
                    and x.receipt_sha256 is not None
                    and len(x.receipt_sha256) == 64
                    and x.released_event is None
                    for x in learned_sex_links(state)
                )
            )
        )
    if (
        trigger is None
        or trigger.play != "mockingbird_sex"
        or trigger.actor != actor
        or trigger.learned_sex_source is None
        or trigger.learned_source is not None
        or trigger.bonded_source is not None
        or trigger.changeling_source is not None
        or not trigger.parties
        or len({x.actor for x in trigger.parties}) != len(trigger.parties)
        or any(x.decision != "accepted" or x.event is None for x in trigger.parties)
    ):
        return False
    return any(
        x.id == trigger.learned_sex_source
        and x.rule_id == SEX
        and x.session == trigger.id
        and x.actor == actor
        and x.target == trigger.parties[0].actor
        and sex_party_refs(x) == tuple(p.actor for p in trigger.parties)
        and (
            x.parties is None
            or (
                tuple((p.actor, p.controller) for p in x.parties)
                == tuple((p.actor, p.controller) for p in trigger.parties)
                and all(
                    p.accepted is True and p.consent_event == actual.event
                    for p, actual in zip(x.parties, trigger.parties, strict=True)
                )
            )
        )
        and x.action == action
        and x.accepted is True
        and x.bound_event is not None
        and x.roll_event is not None
        and x.receipt_sha256 is not None
        and len(x.receipt_sha256) == 64
        and x.released_event is None
        for x in learned_sex_links(state)
    )


def infect(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    target: ActorRef,
    asset: str,
    description: str,
    action: str,
    event: str,
    *,
    storage: GainSource | None = None,
    growth: Growth | None = None,
) -> tuple[GameState, tuple[Followup, ...]]:
    if not _owns_source(original, actor, action):
        raise ValueError("Use this actual original person's owned Sex Play")
    view = resolve(original, target, bindings, require_current_profile=False)
    if target.kind == "pilot":
        from girlframe.engine.m3_janus_storage import alter

        return alter(
            original,
            target,
            asset,
            description,
            action,
            event,
            piloting=view.inside_frame is True
            and view.occupied_frame_instance == view.frame_instance,
            source=storage,
            growth=growth,
        )
    if growth is not None:
        raise ValueError("Sup requires this actual original Pilot's paid current Frame")
    actual = assets(original, target)
    chosen = next((x for x in actual if x.id == asset and not x.void), None)
    if chosen is None or not description.strip() or len(description) > 1200:
        raise ValueError(
            "Rewrite the actual counterpart's uncorrupted Asset with its real Void alteration"
        )
    state = update_assets(
        original,
        target,
        tuple(
            x.model_copy(update={"void": True, "description": description}) if x.id == asset else x
            for x in actual
        ),
        event,
    )
    return state, ()


def starry(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    target: ActorRef,
    capability: Capability,
    action: str,
    event: str,
    observers: tuple[int, ...],
) -> GameState:
    from girlframe.engine.m3_mockingbird_state import CAPABILITIES

    if not _owns_source(original, actor, action) or capability not in CAPABILITIES:
        raise ValueError("Choose one actual conversation capability from the owned printed rule")
    identity = "starry:" + action
    state = give_tag(original, bindings, target, actor, "Starry-Eyed", identity, event, observers)
    grant = Starry(
        id=identity,
        speaker=actor,
        holder=target,
        tag=identity,
        capability=capability,
        source_event=event,
        action=action,
    )
    state.mockingbird = state.mockingbird.model_copy(
        update={"starry": (*state.mockingbird.starry, grant)}
    )
    from girlframe.engine.m3_actor_bonds import bond_ref

    return change(state, bond_ref(state, actor), bond_ref(state, target), 1, event)


def helpless(
    original: GameState, actor: ActorRef, target: ActorRef, action: str, event: str
) -> GameState:
    if not _owns_source(original, actor, action):
        raise ValueError("Only the actual acting original person suffers this source result")
    return exposure(
        make_helpless(original, actor, target, event), actor, target, "low_tag", action, event
    )


def deepen(original: GameState, actor: ActorRef, target: ActorRef, event: str) -> GameState:
    """Keep the source roles, but write the one actual physical Bond endpoint."""
    from girlframe.engine.m3_actor_bonds import bond_ref

    return change(original, bond_ref(original, actor), bond_ref(original, target), 1, event)


def remove_void(
    original: GameState, target: ActorRef, asset: str, description: str, event: str
) -> GameState:
    """Taking corruption away never repairs damage or changes an Asset's origin."""
    actual = assets(original, target)
    chosen = next((x for x in actual if x.id == asset and x.void), None)
    if chosen is None or not description.strip() or len(description) > 1200:
        raise ValueError("Describe the actual existing Asset after its Void is taken away")
    return update_assets(
        original,
        target,
        tuple(
            x.model_copy(
                update={
                    "void": False,
                    "description": description,
                    **({"concealed": False} if "concealed" in type(x).model_fields else {}),
                }
            )
            if x.id == asset
            else x
            for x in actual
        ),
        event,
    )


def write_self_asset(
    original: GameState,
    actor: ActorRef,
    name: str,
    description: str,
    action: str,
    event: str,
    *,
    replace: str | None = None,
    storage: GainSource | None = None,
) -> GameState:
    """The explicit self option writes one new Girl Asset, with actual acquisition caps."""
    from girlframe.engine.m3_core import install

    if not _owns_source(original, actor, action) or not name.strip() or len(name) > 120:
        raise ValueError("Name the one actual self-written Void Asset")
    if not description.strip() or len(description) > 1200 or not event:
        raise ValueError("Describe the actual Void taken into yourself")
    identity = "mock-sex-self:" + action
    if any(x.id == identity for x in assets(original, actor)):
        raise ValueError("This original self-written Asset already exists")
    state = GameState.model_validate_json(original.model_dump_json())
    value = AssetState(
        id=identity, family="girl", name=name, description=description, void=storage is None
    )
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("Use the original caster's actual resources")
        from girlframe.engine.m3_janus_storage import ids as stored_ids
        from girlframe.engine.m3_janus_storage import store

        if replace in stored_ids(original, actor):
            raise ValueError("Do not replace an actual active stored-Void Asset at the cap")
        state.sheets[actor.entity] = install(
            sheet, value, replace=replace, effective_void=stored_ids(state, actor), state=state
        ).sheet
        if storage:
            store(
                state,
                actor,
                asset=identity,
                description=description,
                purchase=storage.purchase,
                action=action,
                step=0,
                choice=storage.choice,
                event=event,
                source_kind=storage.kind,
            )
    elif actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy, update
        from girlframe.engine.m3_void_state import HarpyAsset, HarpyState
        from girlframe.engine.m3_world_state import Asset

        body = harpy(state, actor)
        current = assets(state, actor)
        girls = [x for x in current if x.family == "girl"]
        if len(girls) >= 4:
            candidate = next((x for x in girls if x.id == replace and not x.void), None)
            if candidate is None:
                raise ValueError("At the Girl cap, replace one actual non-Void Girl Asset")
            # A carried object's authority stays at its real Item origin.
            from girlframe.engine.m3_items import actual_asset, same_holder

            held = next(
                (
                    x
                    for x in state.held_items
                    if same_holder(state, x.holder, actor)
                    and (old := actual_asset(state, x)) is not None
                    and old.id == candidate.id
                ),
                None,
            )
            if held is not None:
                state.held_items = [
                    x.model_copy(
                        update={"asset_id": None, "asset_owner": None, "state_event": event}
                    )
                    if x.id == held.id
                    else x
                    for x in state.held_items
                ]
            elif isinstance(body, HarpyState):
                state = update(
                    state, actor, assets=tuple(x for x in body.assets if x.id != replace)
                )
            else:
                assert state.world is not None
                state.world = state.world.model_copy(
                    update={
                        "pilots": tuple(
                            x.model_copy(
                                update={"assets": tuple(y for y in x.assets if y.id != replace)}
                            )
                            if x.id == actor.entity
                            else x
                            for x in state.world.pilots
                        )
                    }
                )
            body = harpy(state, actor)
        elif replace is not None:
            raise ValueError("Do not discard an Asset when no cap replacement is required")
        if isinstance(body, HarpyState):
            state = update(state, actor, assets=(*body.assets, HarpyAsset(**value.model_dump())))
        else:
            assert state.world is not None
            new = Asset(
                id=value.id,
                family="girl",
                name=value.name,
                description=value.description,
                void=True,
            )
            state.world = state.world.model_copy(
                update={
                    "pilots": tuple(
                        x.model_copy(update={"assets": (*x.assets, new)})
                        if x.id == actor.entity
                        else x
                        for x in state.world.pilots
                    )
                }
            )
    else:
        raise ValueError("Only the actual owned Girl or retained Harpy writes this self Asset")
    state.facts.append(
        dict(
            kind="mockingbird_self_asset",
            action=action,
            actor=actor.model_dump_json(),
            asset=identity,
            event=event,
            replace=replace or "",
        )
    )
    return state


def void_criteria(before: GameState, after: GameState, actor: ActorRef) -> tuple[str, ...]:
    """Only genuinely new nonempty family thresholds; no duplicate Harpy or invented Frame."""
    if actor.kind != "pilot":
        return ()
    old = before.sheets.get(actor.entity)
    new = after.sheets.get(actor.entity)
    if old is None or new is None or old.character_id != actor.incarnation:
        raise ValueError("Use the actual original person's source sheets")
    from girlframe.engine.m3_girl_runtime_state import has_rule

    immune_girl = has_rule(new, "girl.mockingbird.risk-factor", "MOCKINGBIRD")
    result = []
    for family in ("girl", "frame"):
        prior = [x for x in assets(before, actor) if x.family == family]
        current = [x for x in assets(after, actor) if x.family == family]
        if (
            current
            and all(x.void for x in current)
            and not (prior and all(x.void for x in prior))
            and (family != "girl" or not immune_girl)
        ):
            result.append(family)
    return tuple(result)


def suppress(
    original: GameState,
    target: ActorRef,
    selected: tuple[str, ...],
    account: str,
    action: str,
    event: str,
) -> GameState:
    """Teach/perform suppression of real corruption; actual Void and its criteria stay present."""
    if not selected or len(set(selected)) != len(selected) or not account.strip():
        raise ValueError("Choose real corruption and describe its actual hiding/suppression")
    actual = assets(original, target)
    valid = {identity for identity, _ in corruption_options(original, target)}
    if not set(selected) <= valid:
        raise ValueError("Hide only actual existing corruption; no imaginary or removed source")
    ids = {x.removeprefix("asset:") for x in selected if x.startswith("asset:")}
    values = tuple(
        x.model_copy(update={"concealed": True})
        if x.id in ids and "concealed" in type(x).model_fields
        else x
        for x in actual
    )
    state = (
        update_assets(original, target, values, event)
        if ids
        else GameState.model_validate_json(original.model_dump_json())
    )
    state.facts.append(
        dict(
            kind="mockingbird_suppression",
            actor=target.model_dump_json(),
            selected="|".join(selected),
            account=account.strip(),
            action=action,
            event=event,
        )
    )
    return state


def npc_void(
    original: GameState,
    target: ActorRef,
    manifestation: str,
    giver: ActorRef | None,
    controller: int,
    action: str,
    event: str,
) -> GameState:
    from uuid import NAMESPACE_URL, uuid5

    from girlframe.engine.m3_npc_void import npc_void_tag

    if manifestation not in ("brain", "bones", "flesh", "abstract") or target.kind != "npc":
        raise ValueError("The actual source Handler chooses one printed NPC manifestation")
    state = GameState.model_validate_json(original.model_dump_json())
    npc = (
        next((x for x in state.world.npcs if x.id == target.entity and x.alive), None)
        if state.world
        else None
    )
    if npc is None or "director" in npc.jobs:
        raise ValueError("Normal NPC physiology only; a Director uses the real Handler source port")
    tag = npc_void_tag(
        str(uuid5(NAMESPACE_URL, event + ":sex-void:" + target.entity)),
        manifestation,
        giver.model_dump_json() if giver else "gm:" + str(controller) + ":" + event,
    )
    assert state.world is not None
    state.world = state.world.model_copy(
        update={
            "npcs": tuple(
                x.model_copy(update={"tags": (*x.tags, tag)}) if x.id == npc.id else x
                for x in state.world.npcs
            )
        }
    )
    state.facts.append(
        dict(
            kind="mockingbird_npc_void",
            actor=target.model_dump_json(),
            tag=tag.id,
            manifestation=manifestation,
            action=action,
            event=event,
        )
    )
    return state


def corruption_options(state: GameState, target: ActorRef) -> tuple[tuple[str, str], ...]:
    """Names identify actual corruption records, never a fabricated Asset from a descriptor."""
    import json
    from uuid import NAMESPACE_URL, uuid5

    result = [("asset:" + x.id, x.name) for x in assets(state, target) if x.void]
    if target.kind == "npc" and state.world:
        from girlframe.engine.m3_fuel_shortage import npc_void_tags

        proven = {
            x["tag"]
            for x in state.facts
            if x.get("kind") == "mockingbird_npc_void"
            and x.get("actor") == target.model_dump_json()
        }
        proven.update(npc_void_tags(state, target))
        for fact in state.facts:
            if fact.get("kind") == "dive_effect" and fact.get("option") == "nearby_npcs_gain_void":
                if any(x.get("npc") == target.entity for x in json.loads(fact["effect"])["npcs"]):
                    proven.add(
                        str(uuid5(NAMESPACE_URL, fact["source_event"] + ":" + target.entity))
                    )
        npc = next((x for x in state.world.npcs if x.id == target.entity and x.alive), None)
        result += [("tag:" + x.id, x.label) for x in (npc.tags if npc else ()) if x.id in proven]
    from girlframe.engine.m3_actor_bonds import bond_ref

    body = bond_ref(state, target)
    result += [
        ("physiology:" + x.id, "Actual localized " + (x.manifestation or "Void"))
        for x in state.handler_void
        if x.body == body and x.void_present and x.phase != "ended"
    ]
    return tuple(result)
