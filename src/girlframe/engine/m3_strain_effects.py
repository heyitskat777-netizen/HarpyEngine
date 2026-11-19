"""Typed application of supported Strain consequences, with no acknowledge fallback."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine import m3_world as world_rules
from girlframe.engine.m2 import GameState, Model, TagState, pair_key
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_benevolent_contact import RULE as BENEVOLENT_CONTACT
from girlframe.engine.m3_benevolent_contact import Contact
from girlframe.engine.m3_benevolent_contact import Play as ContactPlay
from girlframe.engine.m3_berserk_frame import RULE as BERSERK_FRAME
from girlframe.engine.m3_budget_anarchy import REBELLION as REBEL_PROTEST
from girlframe.engine.m3_budget_conversion import RULE as BUDGET_CONVERSION
from girlframe.engine.m3_budget_hearing import RULE as BUDGET_HEARING
from girlframe.engine.m3_budget_sabotage import Pin
from girlframe.engine.m3_bunk_harpy import RULE as BUNK_HARPY
from girlframe.engine.m3_cadre_leak import RULE as CADRE_LEAK
from girlframe.engine.m3_civic_directive import RULES as CIVIC_DIRECTIVES
from girlframe.engine.m3_contraband_state import ContrabandFind
from girlframe.engine.m3_cult_occupation import RULE as CULT_OCCUPATION
from girlframe.engine.m3_doppelganger_reveal import RULE as DOPPELGANGER_REVEAL
from girlframe.engine.m3_foundation_attack import RULE as FOUNDATION_ATTACK
from girlframe.engine.m3_harpy_raid import RULE as HARPY_RAID
from girlframe.engine.m3_npc_interest import RULE as NPC_INTEREST
from girlframe.engine.m3_npc_interest import Timing as InterestTiming
from girlframe.engine.m3_orbital_threat import RULE as ORBITAL_THREAT
from girlframe.engine.m3_pilot_fears import APPEARANCE as PUBLIC_APPEARANCE
from girlframe.engine.m3_pilot_fears import RULE as PILOT_FEARS
from girlframe.engine.m3_rebel_ambush import HUNT_RULE as REBEL_HUNT
from girlframe.engine.m3_rebel_ambush import RULE as REBEL_AMBUSH
from girlframe.engine.m3_rebel_ambush import SIEGE_RULE as REBEL_SIEGE
from girlframe.engine.m3_rebel_base_capture import RULE as REBEL_BASE_CAPTURE
from girlframe.engine.m3_rebel_bond_attack import RULE as REBEL_BOND_ATTACK
from girlframe.engine.m3_rebel_defection import RULE as REBEL_DEFECTION
from girlframe.engine.m3_rebel_escape_offer import RULE as REBEL_ESCAPE_OFFER
from girlframe.engine.m3_rebel_frame_theft import RULE as REBEL_FRAME_THEFT
from girlframe.engine.m3_rebel_strafe import RULE as REBEL_STRAFE
from girlframe.engine.m3_rebel_taunt import RULE as REBEL_TAUNT
from girlframe.engine.m3_rebel_voice import RULE as REBEL_VOICE
from girlframe.engine.m3_refusal_state import RefusalBonus
from girlframe.engine.m3_scientific_observation import Demand, require_orders
from girlframe.engine.m3_supply_state import SupplyLoss
from girlframe.engine.m3_void_revelation import RULE as VOID_REVELATION
from girlframe.engine.m3_void_revelation import Play as RevelationPlay
from girlframe.engine.m3_void_revelation import Revelation
from girlframe.engine.m3_void_rift import RULE as VOID_RIFT
from girlframe.engine.m3_void_signal import RULE as VOID_SIGNAL
from girlframe.engine.m3_world_state import (
    AdversaryPilot,
    Asset,
    CorePlan,
    Faction,
    Gorgon,
    GorgonType,
    Location,
    NpcRecruitment,
    SpriteEscort,
    SpriteEscortDesign,
)

VOID_EXAMINATION = "strain.void.low.6.2"
SPRITE_ESCORT = "strain.void.low.2.2"

SUPPORTED = frozenset(
    {
        "strain.void.low.1.1",
        "strain.void.low.2.1",
        SPRITE_ESCORT,
        PUBLIC_APPEARANCE,
        "strain.void.low.4.1",
        BENEVOLENT_CONTACT,
        "strain.void.low.5.1",
        NPC_INTEREST,
        ORBITAL_THREAT,
        VOID_EXAMINATION,
        "strain.void.high.3.1",
        VOID_REVELATION,
        VOID_RIFT,
        VOID_SIGNAL,
        PILOT_FEARS,
        DOPPELGANGER_REVEAL,
        HARPY_RAID,
        BUNK_HARPY,
        BERSERK_FRAME,
        CULT_OCCUPATION,
        CADRE_LEAK,
        "strain.rebellion.low.1.1",
        "strain.rebellion.low.1.2",
        "strain.rebellion.low.2.2",
        REBEL_STRAFE,
        REBEL_TAUNT,
        REBEL_VOICE,
        REBEL_AMBUSH,
        REBEL_HUNT,
        REBEL_SIEGE,
        REBEL_BASE_CAPTURE,
        REBEL_BOND_ATTACK,
        REBEL_FRAME_THEFT,
        "strain.rebellion.low.5.2",
        REBEL_PROTEST,
        REBEL_ESCAPE_OFFER,
        *CIVIC_DIRECTIVES,
        "strain.rebellion.high.4.2",
        "strain.rebellion.high.5.2",
        "strain.rebellion.low.6.1",
        REBEL_DEFECTION,
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
        BUDGET_CONVERSION,
        BUDGET_HEARING,
        "strain.budget.high.1.1",
        "strain.budget.high.4.2",
        "strain.budget.high.4.1",
        "strain.budget.high.3.2",
        "strain.budget.high.5.1",
        FOUNDATION_ATTACK,
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
    faction_id: str | None = Field(default=None, exclude_if=lambda x: x is None)
    location: Location | None = None
    victim: str | None = None
    foundation_person: Literal["pilot", "handler"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
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
    captured_frame: str | None = Field(default=None, exclude_if=lambda x: x is None)
    fight_channel: int | None = Field(default=None, ge=1, exclude_if=lambda value: value is None)
    revelation_play: RevelationPlay | None = Field(default=None, exclude_if=lambda x: x is None)
    revelation_channel: int | None = Field(default=None, ge=1, exclude_if=lambda x: x is None)
    protest_city: str | None = Field(default=None, exclude_if=lambda x: x is None)
    raid_base: str | None = Field(default=None, exclude_if=lambda x: x is None)
    new_raid_harpy: AdversaryPilot | None = Field(default=None, exclude_if=lambda x: x is None)
    cult_harpy: str | None = Field(default=None, exclude_if=lambda x: x is None)
    new_cult_harpy: AdversaryPilot | None = Field(default=None, exclude_if=lambda x: x is None)
    rift_harpy: AdversaryPilot | None = Field(default=None, exclude_if=lambda x: x is None)
    sprite_escort: SpriteEscortDesign | None = Field(default=None, exclude_if=lambda x: x is None)
    contact_play: ContactPlay | None = Field(default=None, exclude_if=lambda x: x is None)
    contact_channel: int | None = Field(default=None, ge=1, exclude_if=lambda x: x is None)
    defection_recipient: str | None = Field(default=None, exclude_if=lambda x: x is None)
    interest_timing: InterestTiming | None = Field(default=None, exclude_if=lambda x: x is None)
    interest_manifestation: str | None = Field(default=None, exclude_if=lambda x: x is None)
    leak_parties: tuple[ActorRef, ...] = Field(default=(), exclude_if=lambda x: not x)
    leak_report: str | None = Field(default=None, max_length=1200, exclude_if=lambda x: x is None)
    siege_recruits: tuple[AdversaryPilot, ...] = Field(
        default=(), max_length=3, exclude_if=lambda x: not x
    )


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
    revelation: Revelation | None = None,
    contact: Contact | None = None,
) -> GameState:
    if choice.rule_id not in SUPPORTED:
        raise ValueError("UNSUPPORTED_RULE: this Strain effect has no complete typed resolver")
    state = GameState.model_validate_json(original.model_dump_json())
    world = state.world
    if world is None or state.handler is None:
        raise ValueError("Initialize the actual world and appointed Handler first")
    from girlframe.engine.m3_promotional_opportunity import in_responsibility, responsibility_edge

    rule = choice.rule_id
    if rule == VOID_RIFT:
        from girlframe.engine.m3_void_rift import arrive

        fields(choice, {"gorgon", "rift_harpy", "victim"})
        if source_event is None or period_id is None:
            raise ValueError("Recover the actual Strain arrival's source and period")
        return arrive(
            state,
            source_work,
            period_id,
            source_event,
            choice.account,
            choice.gorgon,
            choice.rift_harpy,
            choice.victim,
        )
    if rule == BUDGET_CONVERSION:
        from girlframe.engine.m3_budget_conversion import require_next

        fields(choice, set())
        if source_event is None or period_id is None:
            raise ValueError("Recover the actual High Budget source and original period")
        require_next(state, source_work, period_id, source_event, choice.account.strip())
    elif rule == BUDGET_HEARING:
        fields(choice, {"target", "victim"})
        if not choice.target or choice.victim not in {str(x) for x in state.order}:
            raise ValueError("Choose the original Girl and the fictional Director for the hearing")
    elif rule == BUNK_HARPY:
        fields(choice, {"target"})
        if not choice.target:
            raise ValueError("Choose the actual independently controlled unlinked Harpy")
    elif rule == BERSERK_FRAME:
        from girlframe.engine.m3_berserk_frame import arm as arm_berserk

        fields(choice, {"target", "gorgon", "victim"})
        if (
            source_event is None
            or choice.target not in {str(x) for x in state.order}
            or choice.gorgon is None
            or not choice.victim
        ):
            raise ValueError("Bind the original Frame and actual prepared Aggressive form")
        assert choice.target is not None
        arm_berserk(
            state,
            source_work,
            source_event,
            int(choice.target),
            choice.gorgon,
            choice.victim,
            choice.account.strip(),
        )
    elif rule == FOUNDATION_ATTACK:
        fields(choice, {"target", "victim", "foundation_person"})
        if not choice.target or not choice.victim:
            raise ValueError("Choose the original target and actual Foundation Pilot")
    elif rule == REBEL_SIEGE:
        fields(choice, {"target", "victim", "siege_recruits", "faction"})
        if not choice.target or choice.victim not in (None, "ace", "handler"):
            raise ValueError("Choose the actual occupied base and its original Ace or Handler")
    elif rule == REBEL_AMBUSH:
        from girlframe.engine.m3_rebel_ambush import arm as arm_ambush

        fields(choice, {"target"})
        if not choice.target or source_event is None or period_id is None:
            raise ValueError("Bind the actual Rebel Pilot and original preparing period")
        arm_ambush(
            state,
            source_work,
            period_id,
            source_event,
            ActorRef(kind="external_pilot", entity=choice.target),
            choice.account.strip(),
        )
    elif rule == REBEL_HUNT:
        from girlframe.engine.m3_actor_bonds import current_ref
        from girlframe.engine.m3_rebel_ambush import arm_hunt

        fields(choice, {"target", "victim"})
        if (
            not choice.target
            or source_event is None
            or period_id is None
            or choice.victim not in {str(x) for x in state.order}
        ):
            raise ValueError("Bind the actual Rebel and original target of this pursuit")
        assert choice.victim is not None
        arm_hunt(
            state,
            source_work,
            period_id,
            source_event,
            ActorRef(kind="external_pilot", entity=choice.target),
            current_ref(state, int(choice.victim)),
            choice.account.strip(),
        )
    elif rule == REBEL_BASE_CAPTURE:
        from girlframe.engine.m3_rebel_base_capture import apply as overrun

        fields(choice, {"target", "victim", "captured_frame"})
        if (
            source_event is None
            or not choice.target
            or not choice.victim
            or not choice.captured_frame
        ):
            raise ValueError(
                "Bind the actual base, its Rebel attacker and one original parked Frame"
            )
        state = overrun(
            state,
            source_work,
            source_event,
            choice.target,
            choice.victim,
            choice.captured_frame,
            choice.account.strip(),
        )
        world = state.world
    elif rule == REBEL_BOND_ATTACK:
        from girlframe.engine.m3_rebel_bond_attack import arm as arm_betrayal

        fields(choice, {"target", "faction_id"})
        if not choice.target or not choice.faction_id or source_event is None or period_id is None:
            raise ValueError("Bind the original NPC Bond and their actual Rebel Group")
        arm_betrayal(
            state,
            source_work,
            period_id,
            source_event,
            choice.target,
            choice.faction_id,
            choice.account.strip(),
        )
        world = state.world
    elif rule == REBEL_FRAME_THEFT:
        fields(choice, {"target", "victim"})
        if not choice.target or not choice.victim or source_event is None or period_id is None:
            raise ValueError("Choose the actual base and living Rebel for the original Frame draw")
    elif rule == ORBITAL_THREAT:
        from girlframe.engine.m3_orbital_threat import introduce

        fields(choice, {"gorgon"})
        if choice.gorgon is None or period_id is None or source_event is None:
            raise ValueError("Supply the actual orbital Gorgon, period and event")
        introduce(state, choice.gorgon, source_work, period_id, source_event, choice.account)
        world = state.world
    elif rule == SPRITE_ESCORT:
        fields(choice, {"sprite_escort"})
        if source_event is None or choice.sprite_escort is None:
            raise ValueError("Record the original pending Sprite group and source")
        world = world_rules.update(
            world,
            sprite_escorts=(
                *world.sprite_escorts,
                SpriteEscort(work=source_work, event=source_event, design=choice.sprite_escort),
            ),
        )
    elif rule == BENEVOLENT_CONTACT:
        from girlframe.engine.m3_benevolent_contact import commit as commit_contact

        fields(choice, {"target", "victim", "contact_play", "contact_channel"})
        if (
            contact is None
            or contact.id != source_work
            or contact.grant != source_work
            or contact.event != source_event
            or contact.speaker.actor.entity != choice.target
            or contact.speaker.controller != state.handler
            or contact.recipient.actor.entity != choice.victim
            or contact.play != choice.contact_play
            or contact.account != choice.account.strip()
        ):
            raise ValueError("Recover the performed original Benevolent Gorgon Play")
        commit_contact(state, contact)
    elif rule == NPC_INTEREST:
        fields(choice, {"target", "victim", "interest_timing", "interest_manifestation"})
        if (
            not choice.target
            or choice.victim is None
            or not choice.victim.isascii()
            or not choice.victim.isdecimal()
            or int(choice.victim) not in state.order
            or choice.interest_timing is None
        ):
            raise ValueError("Choose an original NPC, Girl and the timing of her discovery")
    elif rule == VOID_REVELATION:
        from girlframe.engine.m3_void_revelation import commit

        fields(choice, {"revelation_play", "revelation_channel"})
        if (
            revelation is None
            or revelation.id != source_work
            or revelation.event != source_event
            or revelation.play != choice.revelation_play
            or revelation.account != choice.account.strip()
        ):
            raise ValueError("Recover the actual revelation and original scene audience")
        commit(state, revelation)
    elif rule == VOID_EXAMINATION:
        fields(choice, set())
        if period_id is None or source_event is None or not state.order:
            raise ValueError("Bind the required exams to the actual period and its Girls")
    elif rule == VOID_SIGNAL:
        fields(choice, {"target"})
        if (
            period_id is None
            or source_event is None
            or not any(x.id == choice.target and x.alive for x in world.gorgons)
        ):
            raise ValueError("Bind the original living Gorgon to the preparing period")
    elif rule == PUBLIC_APPEARANCE:
        fields(choice, {"target"})
        if not any(
            x.id == choice.target
            and x.kind == "city"
            and x.operational
            and in_responsibility(state, x.cell)
            for x in world.locations
        ):
            raise ValueError("Choose an actual available city for the Cadre's public appearance")
    elif rule == PILOT_FEARS:
        from girlframe.engine.m3_civic_directive import director

        fields(choice, {"target"})
        director(state, choice.target)
    elif rule == DOPPELGANGER_REVEAL:
        from girlframe.engine.m3_doppelganger_reveal import reveal as reveal_disguise

        fields(choice, {"target", "gorgon"})
        if choice.gorgon is None or period_id is None or source_event is None:
            raise ValueError("Recover the original mask revelation in this preparing period")
        state = reveal_disguise(
            state,
            source_work,
            source_event,
            choice.target,
            choice.gorgon,
            choice.account.strip(),
        )
        assert state.world is not None
        world = state.world
    elif rule == HARPY_RAID:
        fields(choice, {"target", "victim", "raid_base", "new_raid_harpy"})
        if (
            not choice.target
            or not choice.raid_base
            or choice.victim is None
            or not choice.victim.isascii()
            or not choice.victim.isdecimal()
            or int(choice.victim) not in state.order
        ):
            raise ValueError("Choose the original Harpy, occupied base and obsession")
    elif rule == CULT_OCCUPATION:
        from girlframe.engine.m3_cult_occupation import occupy

        fields(choice, {"target", "faction", "cult_harpy", "new_cult_harpy"})
        if source_event is None:
            raise ValueError("Recover the original High Void capture event")
        occupy(
            state,
            work=source_work,
            event=source_event,
            site_id=choice.target,
            faction=choice.faction,
            harpy=choice.cult_harpy,
            new=choice.new_cult_harpy,
            account=choice.account.strip(),
        )
        assert state.world is not None
        world = state.world
    elif rule == CADRE_LEAK:
        fields(choice, {"target", "leak_parties", "leak_report"})
        if not choice.target or not choice.leak_parties or not (choice.leak_report or "").strip():
            raise ValueError("Bind the actual incident, original parties and fictional Director")
    elif rule in CIVIC_DIRECTIVES:
        from girlframe.engine.m3_civic_directive import create as create_civic_directive

        fields(choice, {"target", "protest_city"})
        if period_id is None or source_event is None:
            raise ValueError("Recover the original civic directive and Strain period")
        create_civic_directive(
            state,
            rule=rule,
            identity=source_work,
            event=source_event,
            period=period_id,
            speaker=choice.target,
            city=choice.protest_city,
        )
    elif rule == REBEL_STRAFE:
        from girlframe.engine.m3_rebel_strafe import source as strafe_source

        fields(choice, {"target", "victim"})
        strafe_source(state, choice.victim, choice.target)
    elif rule == REBEL_DEFECTION:
        from girlframe.engine.m3_rebel_defection import contact as stage_defection

        fields(choice, {"target", "faction_id", "defection_recipient"})
        if source_event is None or period_id is None:
            raise ValueError("Recover the original preparing defection source")
        stage_defection(
            state,
            identity=source_work,
            event=source_event,
            period=period_id,
            target=choice.target,
            group=choice.faction_id,
            recipient=choice.defection_recipient,
            account=choice.account.strip(),
        )
    elif rule in (REBEL_ESCAPE_OFFER, REBEL_TAUNT, REBEL_VOICE):
        from girlframe.engine.m3_rebel_escape_offer import speaker

        fields(choice, {"target"})
        speaker(state, choice.target)
    elif rule == "strain.rebellion.low.2.2":
        fields(choice, {"target"})
        if (
            contraband is None
            or contraband.id != source_work
            or contraband.period != period_id
            or contraband.base != choice.target
            or contraband.source_event != source_event
            or contraband.taken is not None
            or bool(world.regions)
            and not any(
                x.id == choice.target and in_responsibility(state, x.cell) for x in world.locations
            )
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
        bases = [
            x
            for x in world.locations
            if x.kind == "base" and x.condition != "destroyed" and in_responsibility(state, x.cell)
        ]
        cities = [
            x
            for x in world.locations
            if x.kind == "city" and x.condition != "destroyed" and in_responsibility(state, x.cell)
        ]
        if rule == "strain.void.low.1.1":
            if (
                incoming.gorgon_class != "directed"
                or incoming.goal is None
                or incoming.goal.kind != "location"
                or incoming.goal.entity_id not in {x.id for x in cities}
                or not responsibility_edge(state, incoming.cell)
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
        outcome = world_rules.introduce_gorgon(world, incoming, event=source_event)
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
                if source_event is None:
                    raise ValueError(
                        "The actual Aggressive introduction needs its real source event"
                    )
                from girlframe.engine.m3_gorgon_arrival import aggressive_casualty

                state.world = world
                state = aggressive_casualty(
                    state, incoming, victim, source_work, source_event, choice.account
                )
                world = state.world
                assert world is not None
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
        world = world_rules.arrive_with_sprites(world, returned, source_event)
    elif rule == "strain.rebellion.low.1.1":
        fields(choice, {"target", "faction"})
        city = next(
            (
                x
                for x in world.locations
                if x.id == choice.target
                and x.kind == "city"
                and x.condition != "destroyed"
                and in_responsibility(state, x.cell)
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
            or not in_responsibility(state, location.cell)
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
        from girlframe.engine.m3_actor_bonds import change as change_room_bond
        from girlframe.engine.m3_actor_bonds import current_ref as room_person

        if source_event is not None:
            for room in choice.rooms:
                for i, first in enumerate(room):
                    for second in room[i + 1 :]:
                        state = change_room_bond(
                            state,
                            room_person(state, first),
                            room_person(state, second),
                            1,
                            source_event,
                        )
        else:
            # Preserve source-free numeric-only reducer calls. An existing
            # canonical room edge needs the real event, never a second authority.
            if any(
                {edge.first, edge.second} == {room_person(state, first), room_person(state, second)}
                for room in choice.rooms
                for i, first in enumerate(room)
                for second in room[i + 1 :]
                for edge in state.actor_bonds
            ):
                raise ValueError("Canonical room Bonds need the actual source event")
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
    elif rule in ("strain.budget.high.5.1", REBEL_PROTEST):
        from girlframe.engine.m3_budget_anarchy import create as create_anarchy

        fields(choice, {"target", "faction_id"} if rule == REBEL_PROTEST else {"target"})
        city = next(
            (
                x
                for x in world.locations
                if x.id == choice.target
                and x.kind == "city"
                and x.condition != "destroyed"
                and in_responsibility(state, x.cell)
            ),
            None,
        )
        if city is None:
            raise ValueError("Choose an actual surviving city to fall into anarchy")
        if source_event is None:
            raise ValueError("Record the actual anarchy source event")
        if rule == REBEL_PROTEST and not any(
            faction.id == choice.faction_id and faction.kind == "rebel" and faction.active
            for faction in world.factions
        ):
            raise ValueError("Choose the actual active Rebel faction leading the protest")
        create_anarchy(
            state, source_work, source_event, city.id, choice.account, faction=choice.faction_id
        )
        if rule != REBEL_PROTEST:
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
