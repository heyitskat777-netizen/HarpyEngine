"""Typed application of supported Strain consequences, with no acknowledge fallback."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine import m3_world as world_rules
from girlframe.engine.m2 import GameState, Model, TagState, pair_key
from girlframe.engine.m3_budget_sabotage import Pin
from girlframe.engine.m3_contraband_state import ContrabandFind
from girlframe.engine.m3_refusal_state import RefusalBonus
from girlframe.engine.m3_scientific_observation import Demand, require_orders
from girlframe.engine.m3_supply_state import SupplyLoss
from girlframe.engine.m3_world_state import (
    Asset,
    CorePlan,
    Faction,
    Gorgon,
    GorgonType,
    Location,
    NpcRecruitment,
)

SUPPORTED = frozenset(
    {
        "strain.void.low.1.1",
        "strain.void.low.2.1",
        "strain.void.low.4.1",
        "strain.void.low.5.1",
        "strain.void.high.3.1",
        "strain.rebellion.low.1.1",
        "strain.rebellion.low.1.2",
        "strain.rebellion.low.2.2",
        "strain.rebellion.low.5.2",
        "strain.rebellion.high.4.2",
        "strain.rebellion.high.5.2",
        "strain.rebellion.low.6.1",
        "strain.budget.low.5.2",
        "strain.budget.low.5.1",
        "strain.budget.low.6.1",
        "strain.budget.low.1.1",
        "strain.budget.low.1.2",
        "strain.budget.low.2.1",
        "strain.budget.low.2.2",
        "strain.budget.low.4.2",
        "strain.budget.low.4.1",
        "strain.budget.low.3.2",
        "strain.budget.low.3.1",
        "strain.budget.low.6.2",
        "strain.budget.high.2.2",
        "strain.budget.high.1.1",
        "strain.budget.high.4.2",
        "strain.budget.high.4.1",
        "strain.budget.high.3.2",
        "strain.budget.high.5.1",
        "strain.budget.high.6.1",
    }
)


class TagChoice(Model):
    owner: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=120)


class Choice(Model):
    rule_id: str
    account: str = Field(min_length=1, max_length=2400)
    target: str | None = None
    gorgon: Gorgon | None = None
    faction: Faction | None = None
    location: Location | None = None
    victim: str | None = None
    new_assets: tuple[Asset, ...] = ()
    new_type: GorgonType | None = None
    core_plan: CorePlan | None = None
    rooms: tuple[tuple[int, ...], ...] = ()
    npc_jobs: tuple[str, ...] = ()
    tags: tuple[TagChoice, ...] = ()
    missing_resource: str | None = Field(default=None, max_length=120)
    scientific_demand: Demand | None = None
    function_kind: Literal["auction", "fundraiser", "ball", "orgy"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    cleanup_mode: Literal["scene", "exposure"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    planned_assets: tuple[Pin, ...] = Field(default=(), exclude_if=lambda value: not value)
    fighters: tuple[int, ...] = Field(default=(), exclude_if=lambda value: not value)
    backstory_observers: tuple[int, ...] = Field(default=(), exclude_if=lambda value: not value)
    storage_owner: int | None = Field(default=None, ge=1, exclude_if=lambda value: value is None)
    fight_channel: int | None = Field(default=None, ge=1, exclude_if=lambda value: value is None)


def fields(choice: Choice, allowed: set[str]) -> None:
    defaults = Choice(rule_id=choice.rule_id, account=choice.account)
    for field in type(choice).model_fields:
        if field not in allowed | {"rule_id", "account"} and getattr(choice, field) != getattr(
            defaults, field
        ):
            raise ValueError("This Strain event includes unrelated choices")
    if not choice.account.strip():
        raise ValueError("Record the actual source-specific event context")


def apply(
    original: GameState,
    choice: Choice,
    source_work: str,
    *,
    period_id: str | None = None,
    supply: SupplyLoss | None = None,
    source_event: str | None = None,
    contraband: ContrabandFind | None = None,
    tag_setter_appointment: str | None = None,
    cleanup_index: int | None = None,
    cleanup_rng: Literal["os", "test_injected"] | None = None,
) -> GameState:
    if choice.rule_id not in SUPPORTED:
        raise ValueError("UNSUPPORTED_RULE: this Strain effect has no complete typed resolver")
    state = GameState.model_validate_json(original.model_dump_json())
    world = state.world
    if world is None or state.handler is None:
        raise ValueError("Initialize the actual world and appointed Handler first")
    rule = choice.rule_id
    if rule == "strain.rebellion.low.2.2":
        fields(choice, {"target"})
        if (
            contraband is None
            or contraband.id != source_work
            or contraband.period != period_id
            or contraband.base != choice.target
            or contraband.source_event != source_event
            or contraband.taken is not None
            or any(x.id == source_work for x in state.contraband_finds)
        ):
            raise ValueError("Record one actual private contraband draw and its source period")
        state.contraband_finds.append(contraband)
    elif rule == "strain.rebellion.low.5.2":
        from girlframe.engine.m3_rebel_contact import create as create_contact

        fields(choice, {"target"})
        if period_id is None or source_event is None or choice.target is None:
            raise ValueError("Choose the actual nearby city for this original contact source")
        state = create_contact(
            state, source_work, period_id, source_event, choice.target, choice.account
        )
        world = state.world
    elif rule == "strain.rebellion.high.5.2":
        from girlframe.engine.m3_rebel_backstory import create as create_backstory

        fields(choice, {"tags", "backstory_observers"})
        if source_event is None or len(choice.tags) != 1 or choice.tags[0].owner != state.handler:
            raise ValueError("The actual original Handler supplies its own backstory Tag")
        state = create_backstory(
            state,
            source_work,
            source_event,
            choice.tags[0].label,
            choice.account,
            choice.backstory_observers,
        )
        world = state.world
    elif rule == "strain.rebellion.high.4.2":
        from girlframe.engine.m3_control_ritual import create as create_ritual

        fields(choice, set())
        if period_id is None or source_event is None:
            raise ValueError("Preserve the actual Control Ritual source period")
        state = create_ritual(state, source_work, period_id, source_event, choice.account)
        world = state.world
    elif rule == "strain.rebellion.low.1.2":
        fields(choice, set())
        if (
            period_id is None
            or source_event is None
            or any(x.id == source_work for x in state.refusal_bonuses)
        ):
            raise ValueError("Record one actual new control-slip source and its Strain period")
        assert state.handler is not None
        state.refusal_bonuses.append(
            RefusalBonus(
                id=source_work, period=period_id, handler=state.handler, source_event=source_event
            )
        )
    elif rule == "strain.budget.low.2.2":
        from girlframe.engine.m3_budget_sabotage import create as create_sabotage

        fields(choice, {"planned_assets"})
        if source_event is None:
            raise ValueError("Record the actual private Asset-card source event")
        state = create_sabotage(
            state, source_work, source_event, choice.planned_assets, choice.account
        )
        world = state.world
    elif rule == "strain.budget.low.4.1":
        from girlframe.engine.m3_budget_cleanup import create as create_cleanup

        fields(choice, {"target", "victim", "cleanup_mode"})
        if (
            period_id is None
            or source_event is None
            or choice.target is None
            or choice.victim is None
            or choice.cleanup_mode is None
        ):
            raise ValueError("Choose the actual past mission, site and cleanup route")
        state = create_cleanup(
            state,
            source_work,
            source_event,
            period_id,
            choice.victim,
            choice.target,
            choice.cleanup_mode,
            choice.account,
            cleanup_index,
            cleanup_rng,
        )
        world = state.world
    elif rule == "strain.budget.low.6.1":
        from girlframe.engine.m3_budget_assassination import create as create_assignment

        fields(choice, {"target"})
        if period_id is None or source_event is None or choice.target is None:
            raise ValueError("Choose the actual NPC politician and source period")
        state = create_assignment(
            state, source_work, period_id, source_event, choice.target, choice.account
        )
        world = state.world
    elif rule == "strain.budget.high.6.1":
        from girlframe.engine.m3_budget_storage import create as create_storage

        fields(choice, {"target", "victim", "storage_owner"})
        if (
            period_id is None
            or source_event is None
            or choice.target is None
            or choice.victim is None
            or choice.storage_owner is None
            or tag_setter_appointment is None
        ):
            raise ValueError("Choose the actual original Frame, base and claimed higher-up")
        state = create_storage(
            state,
            source_work,
            period_id,
            source_event,
            choice.storage_owner,
            choice.target,
            choice.victim,
            tag_setter_appointment,
            choice.account,
        )
        world = state.world
    elif rule == "strain.budget.low.5.1":
        from girlframe.engine.m3_budget_visitor import create as create_visit

        fields(choice, {"target"})
        if period_id is None or source_event is None or choice.target is None:
            raise ValueError("Choose the actual higher-up for this source period")
        state = create_visit(
            state, source_work, period_id, source_event, choice.target, choice.account
        )
        world = state.world
    elif rule == "strain.budget.high.4.1":
        from girlframe.engine.m3_budget_fight import create as create_fight

        fields(choice, {"target", "fighters", "fight_channel"})
        if (
            period_id is None
            or source_event is None
            or choice.target is None
            or choice.fight_channel is None
        ):
            raise ValueError("Choose the original fight scene and source period")
        state = create_fight(
            state,
            source_work,
            period_id,
            source_event,
            choice.target,
            choice.fight_channel,
            choice.fighters,
            choice.account,
        )
        world = state.world
    elif rule == "strain.budget.high.4.2":
        from girlframe.engine.m3_budget_candidate import create as create_candidate

        fields(choice, {"target", "victim"})
        if (
            period_id is None
            or source_event is None
            or choice.target is None
            or choice.victim is None
        ):
            raise ValueError("Choose the actual Candidate and assigned Girl for this period")
        state = create_candidate(
            state,
            source_work,
            period_id,
            source_event,
            choice.target,
            int(choice.victim),
            choice.account,
        )
        world = state.world
    elif rule == "strain.budget.low.3.1":
        fields(choice, {"scientific_demand"})
        if choice.scientific_demand is None:
            raise ValueError("Record the actual scientific targets and explicit hiding reviews")
        require_orders(state, choice.scientific_demand, source_work, choice.account)
    elif rule == "strain.budget.low.3.2":
        fields(choice, {"missing_resource"})
        if (
            supply is None
            or supply.id != source_work
            or supply.period != period_id
            or supply.resource != choice.missing_resource
            or any(x.id == source_work for x in state.supply_losses)
        ):
            raise ValueError("The missing shipment needs its actual random draw and period")
        state.supply_losses.append(supply)
    elif rule == "strain.budget.low.4.2":
        from girlframe.engine.m3_repairs import schedule

        fields(choice, set())
        if period_id is None:
            raise ValueError("The repair shortage needs its actual Strain period")
        state.repair_shortages.append(schedule(state, source_work, period_id))
    elif rule in {
        "strain.void.low.1.1",
        "strain.void.low.2.1",
        "strain.void.low.4.1",
        "strain.void.low.5.1",
    }:
        fields(
            choice,
            {"gorgon", "victim"}
            if rule in {"strain.void.low.4.1", "strain.void.low.5.1"}
            else {"gorgon"},
        )
        incoming = choice.gorgon
        if incoming is None or incoming.cell is None:
            raise ValueError("Choose the actual Gorgon, its Assets, Core conditions and map square")
        bases = [x for x in world.locations if x.kind == "base" and x.condition != "destroyed"]
        cities = [x for x in world.locations if x.kind == "city" and x.condition != "destroyed"]
        if rule == "strain.void.low.1.1":
            if (
                incoming.gorgon_class != "directed"
                or incoming.goal is None
                or incoming.goal.kind != "location"
                or incoming.goal.entity_id not in {x.id for x in cities}
                or not any(
                    incoming.cell[i] in (world.board.minimum[i], world.board.maximum[i])
                    for i in (0, 1)
                )
            ):
                raise ValueError(
                    "This Directed Gorgon enters at a map edge and targets a real city"
                )
        elif rule == "strain.void.low.2.1":
            if incoming.gorgon_class not in ("dormant", "erratic") or not any(
                world_rules.distance(incoming.cell, x.cell) == 1 for x in bases
            ):
                raise ValueError("Place a Dormant or Erratic Gorgon in a square beside a real base")
        elif rule == "strain.void.low.4.1":
            if incoming.gorgon_class != "aggressive" or incoming.cell not in {
                x.cell for x in cities
            }:
                raise ValueError("This Aggressive Gorgon emerges in a city")
        else:
            if (
                incoming.gorgon_class != "sprite"
                or incoming.sprite_group
                or incoming.cell not in {x.cell for x in bases}
            ):
                raise ValueError("A single Sprite has entered an actual base")
        outcome = world_rules.introduce_gorgon(world, incoming)
        world = outcome.world
        if rule == "strain.void.low.4.1":
            event_city = next(x for x in cities if x.cell == incoming.cell)
            world = world_rules.update(
                world,
                gorgons=tuple(
                    x.model_copy(
                        update={
                            "collateral_city": event_city.id,
                            "collateral_successes": 0,
                            "collateral_resolved": False,
                        }
                    )
                    if x.id == incoming.id
                    else x
                    for x in world.gorgons
                ),
            )
        if rule in {"strain.void.low.4.1", "strain.void.low.5.1"}:
            victim = next(
                (
                    x
                    for x in world.npcs
                    if x.id == choice.victim and x.alive and x.cell == incoming.cell
                ),
                None,
            )
            if victim is None:
                raise ValueError("Choose an actual living NPC at the event's location")
            if rule == "strain.void.low.4.1":
                from girlframe.engine.m3_actor_state import ActorRef
                from girlframe.engine.m3_battle import category, end_actor_casts
                from girlframe.engine.m3_enforcer import end_grasps
                from girlframe.engine.m3_physical import interrupt_journeys

                ref = ActorRef(kind="npc", entity=victim.id)
                if source_event is None:
                    raise ValueError(
                        "The actual Aggressive introduction needs its real source event"
                    )
                if category(state, ref) == "harpy":
                    raise ValueError(
                        "A captured Harpy Core is not an ordinary NPC introduction victim"
                    )
                state.world = world
                if "director" in victim.jobs:
                    from girlframe.engine.m3_battle_director import die

                    state = die(state, ref, source_event, choice.account)
                else:
                    state = end_actor_casts(
                        end_grasps(
                            interrupt_journeys(state, ref, source_event, choice.account),
                            ref,
                            source_event,
                        ),
                        ref,
                        source_event,
                    )
                    assert state.world is not None
                    state.world = world_rules.update(
                        state.world,
                        npcs=tuple(
                            x.model_copy(update={"alive": False}) if x.id == victim.id else x
                            for x in state.world.npcs
                        ),
                    )
                assert state.world is not None
                world = state.world
                state.facts.append(
                    dict(
                        kind="aggressive_introduction_consumed",
                        source_work=source_work,
                        source_event=source_event,
                        gorgon=incoming.id,
                        followup="aggressive_introduction_npc_death",
                        source_pdf="165",
                        victim=ref.model_dump_json(),
                        original_body=victim.model_dump_json(),
                        account=choice.account,
                    )
                )
            else:
                world = world_rules.update(
                    world,
                    npcs=tuple(
                        x.model_copy(update={"captive_of": incoming.id}) if x.id == victim.id else x
                        for x in world.npcs
                    ),
                )
    elif rule == "strain.void.high.3.1":
        fields(choice, {"target", "new_assets", "new_type", "core_plan"})
        target = next((x for x in world.gorgons if x.id == choice.target and not x.alive), None)
        if (
            target is None
            or choice.new_type is None
            or choice.new_type in target.types
            or choice.core_plan is None
        ):
            raise ValueError(
                "Choose a defeated Gorgon, a distinct additional Type and new Core conditions"
            )
        if len(choice.new_assets) != 2 or any(
            x.family != "gorgon" or x.damaged for x in choice.new_assets
        ):
            raise ValueError("The returning Gorgon gains exactly two distinct intact new Assets")
        returned = target.model_copy(
            update={
                "alive": True,
                "exposed": False,
                "core_strike_failed": False,
                "types": target.types + (choice.new_type,),
                "assets": target.assets + choice.new_assets,
                "core_plan": choice.core_plan,
            }
        )
        world = world_rules.update(
            world,
            gorgons=tuple(
                returned
                if x.id == target.id
                else x.model_copy(update={"types": returned.types})
                if x.follows == target.id
                else x
                for x in world.gorgons
            ),
        )
    elif rule == "strain.rebellion.low.1.1":
        fields(choice, {"target", "faction"})
        city = next(
            (
                x
                for x in world.locations
                if x.id == choice.target and x.kind == "city" and x.condition != "destroyed"
            ),
            None,
        )
        faction = choice.faction
        if (
            city is None
            or faction is None
            or faction.kind != "rebel"
            or not faction.active
            or faction.cells != (city.cell,)
        ):
            raise ValueError("Introduce an active Rebel Group in the selected real city")
        world = world_rules.update(
            world,
            factions=world.factions + (faction,),
            npc_recruitment=world.npc_recruitment
            + (
                NpcRecruitment(
                    id=source_work, source_work=source_work, city=city.id, faction=faction.id
                ),
            ),
        )
    elif rule == "strain.rebellion.low.6.1":
        fields(choice, {"location", "faction"})
        location, faction = choice.location, choice.faction
        if (
            location is None
            or faction is None
            or location.kind != "base"
            or location.allegiance != "rebel"
            or location.condition != "intact"
            or faction.kind != "rebel"
            or not faction.active
            or faction.cells != (location.cell,)
        ):
            raise ValueError(
                "Create an actual Rebel Base and the active Rebel Group controlling its square"
            )
        world = world_rules.update(
            world, locations=world.locations + (location,), factions=world.factions + (faction,)
        )
    elif rule == "strain.budget.low.5.2":
        fields(choice, {"rooms"})
        occupants = [uid for room in choice.rooms for uid in room]
        if (
            any(len(room) < 2 for room in choice.rooms)
            or len(set(occupants)) != len(occupants)
            or set(occupants) != set(state.order)
        ):
            raise ValueError("Assign every current Girl to one room with at least one other Girl")
        for room in choice.rooms:
            for i, first in enumerate(room):
                for second in room[i + 1 :]:
                    key = pair_key(first, second)
                    depth = state.bonds.get(key, 0)
                    if depth == 2:
                        from girlframe.engine.m3_actor_bonds import current_ref
                        from girlframe.engine.m3_leviathan_obsession import allowed_gain

                        for uid in (first, second):
                            state.sheets[str(uid)].heat += allowed_gain(
                                state,
                                current_ref(state, uid),
                                2,
                                "Shared room Intense overflow",
                                source_event or "",
                            )
                            state.sheets[str(uid)].revision += 1
                    else:
                        state.bonds[key] = depth + 1
        world = world_rules.update(world, rooms=choice.rooms)
    elif rule == "strain.budget.low.6.2":
        fields(choice, {"target", "npc_jobs"})
        from girlframe.engine.m3_actor_bonds import current_ref
        from girlframe.engine.m3_actor_bonds import depth as bond_depth
        from girlframe.engine.m3_actor_state import ActorRef
        from girlframe.engine.m3_handler_consequences import active_handler

        people = [
            current_ref(state, uid)
            for uid in state.order
            if state.sheets[str(uid)].character_id is not None
        ]
        handler = active_handler(state)
        if handler is not None:
            people.append(handler)
        npc = next(
            (
                x
                for x in world.npcs
                if x.id == choice.target
                and x.alive
                and (
                    x.bonds
                    or any(
                        bond_depth(state, ActorRef(kind="npc", entity=x.id), person) > 0
                        for person in people
                    )
                )
            ),
            None,
        )
        if npc is None or not choice.npc_jobs or choice.npc_jobs == npc.jobs:
            raise ValueError(
                "Select an actual living NPC Bond and its changed post-firing playbook"
            )
        world = world_rules.update(
            world,
            npcs=tuple(
                x.model_copy(update={"jobs": choice.npc_jobs, "employment": "unemployed"})
                if x.id == npc.id
                else x
                for x in world.npcs
            ),
        )
    elif rule == "strain.budget.high.1.1":
        fields(choice, {"target"})
        if not choice.target or not period_id or not source_event:
            raise ValueError("Choose a separately played Director for the actual meeting")
        from girlframe.engine.m3_budget_director import create as create_meeting

        state = create_meeting(
            state, source_work, period_id, source_event, choice.target, choice.account
        )
        world = state.world
        assert world is not None
    elif rule == "strain.budget.low.2.1":
        fields(choice, {"target", "function_kind"})
        if not choice.target or not choice.function_kind or not period_id or not source_event:
            raise ValueError("Choose the actual political patron and function")
        from girlframe.engine.m3_political_function import create as create_function

        state = create_function(
            state,
            source_work,
            period_id,
            source_event,
            choice.target,
            choice.function_kind,
            choice.account,
        )
        world = state.world
        assert world is not None
    elif rule == "strain.budget.low.1.2":
        fields(choice, {"target", "victim"})
        if not choice.target or not choice.victim or not source_event or not period_id:
            raise ValueError("Choose the original Girl and existing rich patron for this result")
        from girlframe.engine.m3_budget_patron import create

        state = create(state, source_work, choice.target, choice.victim, period_id, source_event)
        world = state.world
        assert world is not None
    elif rule in ("strain.budget.high.2.2", "strain.budget.low.1.1"):
        assert state.handler is not None
        fields(choice, {"tags"})
        photoshoot = rule == "strain.budget.low.1.1"
        expected = set(state.order) | (set() if photoshoot else {state.handler})
        if photoshoot and (tag_setter_appointment is None or not source_event):
            raise ValueError("The actual public-perception Tags need the appointed human's source")
        if len(choice.tags) != len(expected) or {x.owner for x in choice.tags} != expected:
            raise ValueError(
                "Give exactly one source-authored Tag to every required original participant"
            )
        for selected in choice.tags:
            if not selected.label.strip():
                raise ValueError("Describe each actual supply-shortage Tag")
            tag = TagState(
                id=str(uuid5(NAMESPACE_URL, source_work + ":tag:" + str(selected.owner))),
                label=selected.label,
                giver=state.handler,
                observers=tuple(state.order) + (state.handler,),
                gm_setter_appointment=tag_setter_appointment if photoshoot else None,
            )
            if selected.owner == state.handler:
                state.handler_tags.append(tag)
            else:
                state.sheets[str(selected.owner)].tags.append(tag)
                state.sheets[str(selected.owner)].revision += 1
    elif rule == "strain.budget.high.3.2":
        fields(choice, {"faction"})
        faction = choice.faction
        if (
            faction is None
            or faction.kind != "political"
            or not faction.active
            or not faction.cells
        ):
            raise ValueError(
                "Define the actual political faction, its map area and sanction problems"
            )
        world = world_rules.update(
            world,
            factions=world.factions
            + (faction.model_copy(update={"description": choice.account.strip()}),),
        )
    elif rule == "strain.budget.high.5.1":
        from girlframe.engine.m3_budget_anarchy import create as create_anarchy

        fields(choice, {"target"})
        city = next(
            (
                x
                for x in world.locations
                if x.id == choice.target and x.kind == "city" and x.condition != "destroyed"
            ),
            None,
        )
        if city is None:
            raise ValueError("Choose an actual surviving city to fall into anarchy")
        if source_event is None:
            raise ValueError("Record the actual anarchy source event")
        create_anarchy(state, source_work, source_event, city.id, choice.account)
        world = world_rules.update(
            world,
            locations=tuple(
                x.model_copy(update={"blocked_by": x.blocked_by + (source_work,)})
                if x.id == city.id
                else x
                for x in world.locations
            ),
        )
    else:
        raise ValueError("UNSUPPORTED_RULE: missing Strain effect application")
    state.world = world
    state.facts.append(
        {
            "kind": "strain_effect_applied",
            "source_work": source_work,
            "rule_id": rule,
            "account": choice.account.strip(),
        }
    )
    return state
