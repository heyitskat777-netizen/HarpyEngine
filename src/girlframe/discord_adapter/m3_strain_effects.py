"""Owned native inputs for actual supported Strain effects, bound to saved work."""

import asyncio
from collections.abc import Callable
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_world import TYPES, coordinates, squares
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_benevolent_contact import PLAYS as CONTACT_PLAYS
from girlframe.engine.m3_benevolent_contact import RULE as BENEVOLENT_CONTACT
from girlframe.engine.m3_berserk_frame import RULE as BERSERK_FRAME
from girlframe.engine.m3_berserk_frame import eligible as berserk_frames
from girlframe.engine.m3_budget_anarchy import REBELLION as REBEL_PROTEST
from girlframe.engine.m3_budget_hearing import RULE as BUDGET_HEARING
from girlframe.engine.m3_bunk_harpy import RULE as BUNK_HARPY
from girlframe.engine.m3_cadre_leak import RULE as CADRE_LEAK
from girlframe.engine.m3_civic_directive import PROTEST as CIVIC_PROTEST
from girlframe.engine.m3_civic_directive import RULES as CIVIC_DIRECTIVES
from girlframe.engine.m3_cult_occupation import RULE as CULT_OCCUPATION
from girlframe.engine.m3_doppelganger_reveal import RULE as DOPPELGANGER_REVEAL
from girlframe.engine.m3_foundation_attack import RULE as FOUNDATION_ATTACK
from girlframe.engine.m3_gorgon_catalog import ASSETS
from girlframe.engine.m3_harpy_raid import RULE as HARPY_RAID
from girlframe.engine.m3_npc_interest import RULE as NPC_INTEREST
from girlframe.engine.m3_npc_void import MANIFESTATIONS
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
from girlframe.engine.m3_scientific_observation import Demand
from girlframe.engine.m3_strain_effects import SPRITE_ESCORT, Choice, TagChoice
from girlframe.engine.m3_void_revelation import PLAYS as REVELATIONS
from girlframe.engine.m3_void_revelation import RULE as VOID_REVELATION
from girlframe.engine.m3_void_rift import RULE as VOID_RIFT
from girlframe.engine.m3_void_signal import RULE as VOID_SIGNAL
from girlframe.engine.m3_void_spread import RULE as VOID_SPREAD
from girlframe.engine.m3_world import CLASS_ASSETS, distance
from girlframe.engine.m3_world_state import (
    NPC_JOBS,
    AdversaryPilot,
    Asset,
    CorePlan,
    Faction,
    Goal,
    Gorgon,
    Location,
    SpriteEscortDesign,
)
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

WAIT = (("pending", "Complete the earlier choices first"),)


class DependentForm(NativeForm):
    def __init__(
        self,
        owner: int,
        title: str,
        instructions: str,
        build: Callable[[dict[str, Any]], list[Field]],
        submit: Any,
    ):
        self.build_fields = build
        super().__init__(owner, title, instructions, build({}), submit)

    def controls(self) -> None:
        self.fields = self.build_fields(self.values)
        for field in self.fields:
            if field.options and field.key in self.values:
                selected = self.values[field.key]
                if len(selected) > field.maximum or not set(selected) <= {
                    x[0] for x in field.options
                }:
                    self.values.pop(field.key)
        super().controls()


def stable(work: str, part: str) -> str:
    return str(uuid5(NAMESPACE_URL, work + ":" + part))


def options(rows: list[dict[str, Any]], *, kind: str | None = None) -> tuple[tuple[str, str], ...]:
    return (
        tuple((x["id"], x["name"]) for x in rows if kind is None or x.get("kind") == kind) or WAIT
    )


async def open_effect(
    interaction: discord.Interaction, service: EffectService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data.get("foundation_attention"):
        await reply(
            interaction, "This saved result still needs its Foundation consequences reviewed."
        )
        return
    if insurgent := data.get("pending_insurgent"):
        from girlframe.discord_adapter.m3_rebel_funding import open_participation
        from girlframe.services.m3_rebel_funding import FundingService

        await open_participation(interaction, FundingService(service.strain), insurgent)
        return
    if captured := data.get("captured_base"):
        await reply(
            interaction,
            "The base fell and the original parked Frame entered Rebel custody. "
            f"Prisoners freed: {captured['freed']}. Staff killed: {captured['dead']}.",
        )
        return
    if data.get("awaiting_rebel_voice"):
        await reply(
            interaction,
            "The original Rebel controller can finish the voice from their private Inbox.",
        )
        return
    if data.get("awaiting_budget_hearing"):
        await reply(interaction, "The original parties have the private hearing in their Inbox.")
        return
    if data.get("awaiting_bunk_harpy"):
        await reply(interaction, "The encounter is awaiting a private appearance.")
        return
    if data.get("awaiting_rebel_bond"):
        await reply(interaction, "The original betrayal remains open in the private Inbox.")
        return
    if data.get("awaiting_rebel_siege"):
        from girlframe.discord_adapter.m3_rebel_ambush import open_siege
        from girlframe.services.m3_rebel_ambush import SiegeService

        await open_siege(interaction, SiegeService(service.strain), identity)
        return
    if data.get("awaiting_foundation_attack"):
        await reply(interaction, "Review the original attack in your private Inbox.")
        return
    if data.get("awaiting_frame_theft"):
        await reply(interaction, "The original Frame theft is pending in the private Inbox.")
        return
    if data["rule_id"] == VOID_SPREAD:
        await open_spread(interaction, service, data, identity)
        return
    if data["awaiting_rebel_offer"]:
        await reply(interaction, "The actual Rebel controller has the private offer request.")
        return
    if data["awaiting_civic_directive"]:
        await reply(
            interaction, "The fictional Director's controller has the private order request."
        )
        return
    if data["awaiting_void_signal"]:
        await reply(interaction, "The original recipient's Void consequence is still pending.")
        return
    if data["awaiting_pilot_fears"]:
        await reply(
            interaction,
            "The Cadre's city appearance is pending in the original participants' Inbox."
            if data["rule_id"] == PUBLIC_APPEARANCE
            else "The original Director and Cadre have the demand in their Inbox.",
        )
        return
    if data["awaiting_harpy_raid"]:
        await reply(interaction, "The Harpy's completed Assault is required in the original raid.")
        return
    if data["awaiting_cadre_leak"]:
        await reply(interaction, "The actual leak stays pending. Review its private case.")
        return
    if data["awaiting_npc_interest"]:
        await reply(interaction, "The original discovery and Void gain are in the private Inbox.")
        return
    if data["awaiting_rebel_strafe"]:
        await reply(interaction, "The original Rebel's physical pass is pending in the Inbox.")
        return
    if data["awaiting_rebel_taunt"]:
        await reply(
            interaction, "Review the radio transcript and original Handler Tag in the Inbox."
        )
        return
    if data["rule_id"] == "strain.budget.high.1.2":
        from girlframe.discord_adapter.m3_fuel_shortage import open_fuel_shortage
        from girlframe.services.m3_fuel_shortage import FuelService

        await open_fuel_shortage(interaction, FuelService(service.game), identity)
        return
    if data["rule_id"] == "strain.rebellion.low.4.2":
        from girlframe.discord_adapter.m3_prisoner_escape import open_prisoner_escape
        from girlframe.services.m3_prisoner_escape import PrisonerEscapeService

        await open_prisoner_escape(interaction, PrisonerEscapeService(service.strain), identity)
        return
    if data["rule_id"] == "strain.void.low.1.2":
        from girlframe.discord_adapter.m3_void_frame_entry import open_void_frame_entry
        from girlframe.services.m3_void_frame_entry import VoidFrameEntryService

        await open_void_frame_entry(interaction, VoidFrameEntryService(service.strain), identity)
        return
    if data["rule_id"] == "strain.void.low.3.1":
        from girlframe.discord_adapter.m3_patrol_harpy import open_patrol_harpy
        from girlframe.services.m3_patrol_harpy import PatrolHarpyService

        await open_patrol_harpy(interaction, PatrolHarpyService(service.strain), identity)
        return
    try:
        build, apply, instructions = await asyncio.to_thread(
            effect_form,
            viewer,
            service,
            identity,
            ((str(interaction.channel_id), "Use this Play scene"),),
        )
    except WorkflowError as error:
        await reply(interaction, str(error))
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        return await asyncio.to_thread(
            apply, viewer_from_interaction(current), str(current.id), values
        )

    form = DependentForm(
        viewer.user_id, "Apply the saved Strain event", instructions, build, submit
    )
    await reply(interaction, form.text(), form)


async def open_spread(
    interaction: discord.Interaction, service: EffectService, data: dict[str, Any], identity: str
) -> None:
    spread = data["spread"]
    if spread and spread["scope_event"]:
        from girlframe.discord_adapter.m3_void_spread import open_application

        await open_application(interaction, service, data, identity)
        return
    fields = (
        [Field("squares", "Connected map squares, one x,y per line", paragraph=True)]
        if spread
        else [Field("roll", "Roll the printed area dice", (("yes", "Roll 2d6"),))]
    )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        cells = (
            tuple(coordinates(line) for line in values["squares"].splitlines() if line.strip())
            if spread
            else None
        )
        result = await asyncio.to_thread(
            service.prepare_spread,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            data["game_revision"],
            cells=cells,
        )
        if cells is None:
            count = sum(result["spread"]["faces"])
            return f"The roll covers {count} squares. Reopen this request to choose the area."
        return "The connected area is saved. Reopen it to apply each occupant's Void gain."

    form = NativeForm(
        interaction.user.id,
        "Prepare the High Void spread",
        f"Use the saved total of {sum(spread['faces'])} squares."
        if spread
        else "Save the two actual dice once.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


def effect_form(
    viewer: GuildViewer,
    service: EffectService,
    identity: str,
    channels: tuple[tuple[str, str], ...] = WAIT,
) -> tuple[
    Callable[[dict[str, Any]], list[Field]],
    Callable[[GuildViewer, str, dict[str, Any]], str],
    str,
]:
    """Return the native field builder and typed commit for the authorized saved work."""
    data = service.get(viewer, identity)
    if data["state"] != "pending":
        raise WorkflowError(
            "This effect is already applied. Reopen Off-Duty for current required work."
        )
    if not data["supported"]:
        raise WorkflowError(
            "This event awaits its specific rules support. Its saved result remains required work."
        )
    snapshot = WorldService(service.strain.missions).get(viewer, private=True)
    world = snapshot["world"]
    if world is None:
        raise WorkflowError("Initialize the campaign map first, then reopen this event.")
    if snapshot["game_revision"] != data["game_revision"]:
        raise WorkflowError("STALE_STATE: reopen the changed world before reviewing this effect.")
    with service.store.engine.connect() as c:
        from girlframe.services.m2_state import load_state

        service.game.authorize(c, viewer, game=False)
        service.strain.missions._handler(c, viewer)
        state = load_state(c, service.store.campaign_id)
    if state.revision != data["game_revision"] or state.handler is None:
        raise WorkflowError("STALE_STATE: reopen this changed event.")
    handler = state.handler
    rule = data["rule_id"]
    bunk_harpies: tuple[tuple[str, str], ...] = ()
    if rule == BUNK_HARPY:
        from girlframe.services.m3_bunk_harpy import candidates

        bunk_harpies = candidates(state, viewer)
        if not bunk_harpies:
            raise WorkflowError("Recover a living unlinked Harpy under independent control.")
    from girlframe.engine.m3_promotional_opportunity import in_responsibility, responsibility_edge

    regional_locations = [
        x for x in world["locations"] if in_responsibility(state, (x["cell"][0], x["cell"][1]))
    ]
    if rule in ("strain.budget.low.1.2", "strain.budget.low.2.1") and not any(
        x["alive"] and "patron" in x["jobs"] for x in world["npcs"]
    ):
        raise WorkflowError("Introduce the actual patron, then reopen this result.")
    orbital = rule == ORBITAL_THREAT
    berserk = rule == BERSERK_FRAME
    disguise = rule == DOPPELGANGER_REVEAL
    rift = rule == VOID_RIFT
    new_raid_actor = stable(identity, "new raid Harpy")
    new_cult_actor = stable(identity, "new cult Harpy")
    spawned = rule in {
        "strain.void.low.1.1",
        "strain.void.low.2.1",
        "strain.void.low.4.1",
        "strain.void.low.5.1",
        ORBITAL_THREAT,
        DOPPELGANGER_REVEAL,
        BERSERK_FRAME,
    }
    gorgons = {x["id"]: x for x in world["gorgons"]}
    past_missions = []
    if rule == "strain.budget.low.4.1":
        past_missions = [
            x for x in service.strain.missions.list(viewer) if x["phase"] == "complete"
        ]
        if not past_missions:
            raise WorkflowError("This cleanup needs an actual completed past mission first.")

    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_battle import category
    from girlframe.engine.m3_budget_sabotage import Pin
    from girlframe.engine.m3_doppelganger_reveal import original_bonds
    from girlframe.engine.m3_rebel_ambush import attacker as ambush_attacker

    ambushers = []
    if rule in (REBEL_AMBUSH, REBEL_HUNT):
        for pilot in world["pilots"]:
            actor = ActorRef(kind="external_pilot", entity=pilot["id"])
            try:
                if ambush_attacker(state, actor) != handler:
                    ambushers.append((pilot["id"], pilot["name"]))
            except ValueError:
                continue
    from girlframe.engine.m2 import PilotSheet
    from girlframe.engine.m3_rebel_base_capture import frames as at_base
    from girlframe.engine.m3_rebel_base_capture import rebel as overrun_attacker
    from girlframe.engine.m3_rebel_base_capture import site as overrun_site

    overrun_bases = {}
    if rule == REBEL_BASE_CAPTURE:
        for location in regional_locations:
            try:
                base = overrun_site(state, location["id"])
            except ValueError:
                continue
            parking = at_base(state, base)
            if parking:
                overrun_bases[base.id] = (base, parking)
    from girlframe.engine.m3_rebel_frame_theft import base as theft_base
    from girlframe.engine.m3_rebel_frame_theft import thief as theft_actor

    theft_bases = {}
    if rule in (REBEL_FRAME_THEFT, REBEL_SIEGE, FOUNDATION_ATTACK):
        for location in regional_locations:
            try:
                eligible_base = theft_base(state, location["id"])
            except ValueError:
                continue
            theft_bases[eligible_base.id] = eligible_base

    siege_seed = rule == REBEL_SIEGE and not any(
        x["kind"] == "rebel" and x["alive"] for x in world["pilots"]
    )
    siege_groups: tuple[tuple[str, str], ...] = ()
    siege_controllers: tuple[tuple[str, str], ...] = ()
    if siege_seed:
        from girlframe.services.m3_npc_roles import NpcRoleService

        siege_groups = tuple(
            (x["id"], x["name"]) for x in world["factions"] if x["kind"] == "rebel" and x["active"]
        )
        ace = str(state.order[0]) if state.order else None
        siege_controllers = tuple(
            (uid, label)
            for uid, label in NpcRoleService(WorldService(service.strain.missions)).members(viewer)[
                "members"
            ]
            if uid != ace
        )

    foundation_pilots = []
    foundation_people: dict[str, tuple[str, str]] = {}
    foundation_labels: list[tuple[str, str]] = []
    if rule == FOUNDATION_ATTACK:
        from girlframe.engine.m3_foundation_attack import pilot as foundation_actor

        if handler is not None:
            foundation_people["handler"] = ("handler", str(handler))
            foundation_labels.append(("handler", "The original Handler"))
        for uid in state.order:
            token = "girl:" + str(uid)
            foundation_people[token] = ("pilot", str(uid))
            foundation_labels.append((token, state.sheets[str(uid)].callsign))
        for candidate in world["pilots"]:
            try:
                attacker = foundation_actor(state, candidate["id"])
            except ValueError:
                continue
            foundation_pilots.append((attacker.id, attacker.name))

    masks = (
        {
            x.id: x
            for x in state.world.npcs
            if x.alive
            and x.controller == handler
            and "director" not in x.jobs
            and original_bonds(state, x)
        }
        if disguise and state.world
        else {}
    )
    parties = {}
    if rule == CADRE_LEAK:
        parties = {
            current_ref(state, uid): state.sheets[str(uid)].callsign for uid in state.order
        } | {
            ActorRef(kind="npc", entity=npc["id"]): npc["name"]
            for npc in world["npcs"]
            if npc["alive"]
        }
    parties_by_token = {ref.token: ref for ref in parties}

    asset_pins = {}
    asset_labels = {}
    if rule == "strain.budget.low.2.2":
        for uid in state.order:
            sheet = state.sheets[str(uid)]
            for asset in sheet.assets:
                if asset.concealed:
                    continue
                pin = Pin(owner=current_ref(state, uid), asset=asset.id)
                asset_pins[pin.token] = pin
                asset_labels[pin.token] = sheet.callsign + " · " + asset.name

    def build(values: dict[str, Any]) -> list[Field]:
        fields: list[Field] = []
        if rule == REBEL_STRAFE:
            rebels = {x["id"] for x in world["factions"] if x["kind"] == "rebel" and x["active"]}
            fields += [
                Field(
                    "strafe_pilot",
                    "Which actual Rebel Pilot strafes?",
                    options(
                        [
                            x
                            for x in world["pilots"]
                            if x["alive"]
                            and x["kind"] == "rebel"
                            and x["custody"] == "free"
                            and x["faction"] in rebels
                        ]
                    ),
                ),
                Field(
                    "strafe_base",
                    "Which Foundation base is nearby?",
                    options(
                        [
                            x
                            for x in regional_locations
                            if x["kind"] == "base"
                            and x["allegiance"] == "foundation"
                            and x["condition"] != "destroyed"
                            and not any(
                                x.get(key)
                                for key in ("blocked_by", "fallout_sources", "control_loss")
                            )
                        ]
                    ),
                ),
            ]
        if rule == NPC_INTEREST:
            fields += [
                Field(
                    "interest_npc",
                    "Which ordinary NPC takes an interest?",
                    options(
                        [
                            x
                            for x in world["npcs"]
                            if x["alive"]
                            and x["captive_of"] is None
                            and x["controller"] == handler
                            and "director" not in x["jobs"]
                            and x.get("source_kind") is None
                        ]
                    ),
                ),
                Field(
                    "interest_girl",
                    "Which Girl will find them?",
                    tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order),
                ),
                Field(
                    "interest_timing",
                    "When does the Girl find the NPC?",
                    (("before", "Just before corruption"), ("after", "After corruption")),
                ),
            ]
            if values.get("interest_timing") == ("after",):
                fields.append(
                    Field(
                        "interest_manifestation",
                        "Which Void manifestation occurs first?",
                        tuple((x, "Void of the " + x) for x in MANIFESTATIONS),
                    )
                )
        if rule == SPRITE_ESCORT:
            fields += [
                Field("sprite_name", "Name the Sprite group"),
                Field("sprite_first", "First group Asset"),
                Field("sprite_second", "Second group Asset"),
                Field(
                    "sprite_core",
                    "Which Assets protect its Core?",
                    (("first", "The first Asset"), ("both", "Both Assets")),
                ),
                Field("sprite_weakness", "Describe the Core weakness", paragraph=True),
            ]
        if rule == BENEVOLENT_CONTACT:
            fields += [
                Field(
                    "contact_gorgon",
                    "Which joined Benevolent Gorgon speaks?",
                    options(
                        [
                            x
                            for x in world["gorgons"]
                            if x["alive"] and x["gorgon_class"] == "benevolent"
                        ]
                    ),
                ),
                Field(
                    "contact_girl",
                    "Which Girl does it actually address?",
                    tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order),
                ),
                Field("contact_channel", "Where does it make the Play?", channels),
                Field("contact_play", "Which printed Play does it gain and make?", CONTACT_PLAYS),
            ]
        if rule == CULT_OCCUPATION:
            sites = [
                x
                for x in regional_locations
                if x["condition"] != "destroyed"
                and not any(
                    x.get(key)
                    for key in (
                        "blocked_by",
                        "fallout_sources",
                        "control_loss",
                        "protection_sources",
                    )
                )
            ]
            harpies = {
                x["id"]: x["name"] for x in world["pilots"] if x["kind"] == "harpy" and x["alive"]
            }
            harpies.update({x.id: x.name for x in state.harpy_states if x.alive})
            harpies[new_cult_actor] = "Create a Harpy for this cult"
            fields += [
                Field("cult_site", "Which location does the cult take over?", options(sites)),
                Field("cult_name", "Name of the Gorgon-worshipping cult"),
                Field("cult_harpy", "Which Harpy does the cult venerate?", tuple(harpies.items())),
            ]
            if values.get("cult_harpy") == (new_cult_actor,):
                fields += [
                    Field("harpy_name", "Harpy name"),
                    Field("harpy_frame", "Current Frame description", paragraph=True),
                    Field("girl_component", "Known Girl-body component"),
                    Field("frame_component", "Known Frame component"),
                ]
        if rule == HARPY_RAID:
            bases = [
                x
                for x in regional_locations
                if x["kind"] == "base"
                and x["allegiance"] == "foundation"
                and x["condition"] != "destroyed"
            ]
            harpies = {
                x["id"]: x["name"] for x in world["pilots"] if x["kind"] == "harpy" and x["alive"]
            }
            harpies.update({x.id: x.name for x in state.harpy_states if x.alive})
            harpies.setdefault(new_raid_actor, "Introduce a Harpy for this raid")
            fields += [
                Field("raid_base", "Which occupied Foundation base?", options(bases)),
                Field(
                    "harpy",
                    "Which real Harpy attacks?",
                    tuple(harpies.items()),
                ),
                Field(
                    "obsession",
                    "Which original Girl is the object of the obsession?",
                    tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order),
                ),
            ]
            if values.get("harpy") == (new_raid_actor,):
                fields += [
                    Field("harpy_name", "Harpy name"),
                    Field("harpy_frame", "Current Frame description", paragraph=True),
                    Field("girl_component", "Known Girl-body component"),
                    Field("frame_component", "Known Frame component"),
                ]
        if rule == VOID_SIGNAL:
            fields.append(
                Field(
                    "signal",
                    "Which original Gorgon reaches out?",
                    options([x for x in world["gorgons"] if x["alive"]]),
                )
            )
        if rule == PUBLIC_APPEARANCE:
            fields.append(
                Field(
                    "appearance_city",
                    "Which city hosts the Cadre's public appearance?",
                    options(
                        [
                            x
                            for x in regional_locations
                            if x["kind"] == "city"
                            and x["condition"] != "destroyed"
                            and not any(
                                x.get(key)
                                for key in ("blocked_by", "fallout_sources", "control_loss")
                            )
                        ]
                    ),
                )
            )
        if rule in CIVIC_DIRECTIVES or rule in (PILOT_FEARS, CADRE_LEAK, BUDGET_HEARING):
            fields.append(
                Field(
                    "civic_director",
                    "Who actually plays the fictional Director?",
                    options(
                        [
                            x
                            for x in world["npcs"]
                            if x["alive"]
                            and x["captive_of"] is None
                            and "director" in x["jobs"]
                            and x["controller"] != handler
                            and (
                                rule != BUDGET_HEARING
                                or str(x["controller"]) != values.get("hearing_girl", (None,))[0]
                            )
                        ]
                    ),
                )
            )
            if rule == CIVIC_PROTEST:
                fields.append(
                    Field(
                        "protest_city",
                        "Which nearby operational city holds the protest?",
                        options(
                            [
                                x
                                for x in regional_locations
                                if x["kind"] == "city"
                                and x["condition"] != "destroyed"
                                and not x["blocked_by"]
                            ]
                        ),
                    )
                )
        if rule == BUDGET_HEARING:
            fields.append(
                Field(
                    "hearing_girl",
                    "Which original Girl must attend alone?",
                    tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order)
                    or WAIT,
                )
            )
        if rule == BUNK_HARPY:
            fields.append(
                Field("bunk_harpy", "Which unlinked Harpy comes to the base?", bunk_harpies)
            )
        if rule == CADRE_LEAK:
            fields.append(
                Field(
                    "parties",
                    "Who actually caused the leak? These choices stay private.",
                    tuple((ref.token, label) for ref, label in parties.items()) or WAIT,
                    maximum=min(25, len(parties)) if parties else 1,
                )
            )
            fields.append(Field("leak_report", "What information becomes public?", paragraph=True))
        if rule == VOID_REVELATION:
            fields += [
                Field("revelation", "Which printed revelation do you make?", REVELATIONS),
                Field("revelation_scene", "Where was it actually spoken?", channels),
            ]
        if rule in (REBEL_ESCAPE_OFFER, REBEL_TAUNT, REBEL_VOICE):
            rebels = {x["id"] for x in world["factions"] if x["kind"] == "rebel" and x["active"]}
            fields.append(
                Field(
                    "rebel_handler",
                    "Which Rebel Handler makes the radio call?"
                    if rule == REBEL_TAUNT
                    else "Which Rebel Handler initiates the private contact?",
                    options(
                        [
                            x
                            for x in world["npcs"]
                            if "handler" in x["jobs"]
                            and x["alive"]
                            and x.get("captive_of") is None
                            and x.get("faction") in rebels
                            and x["controller"] != handler
                        ]
                    ),
                )
            )
        if rule in (REBEL_AMBUSH, REBEL_HUNT):
            fields.append(
                Field(
                    "ambusher",
                    "Which original Rebel launches the surprise attack?",
                    tuple(ambushers) or WAIT,
                )
            )
        if rule == REBEL_HUNT:
            chosen = values.get("ambusher", (None,))[0]
            counterpart = next(
                (str(x["controller"]) for x in world["pilots"] if x["id"] == chosen), None
            )
            fields.append(
                Field(
                    "hunt_victim",
                    "Which original Girl is pursued?",
                    tuple(
                        (str(uid), state.sheets[str(uid)].callsign)
                        for uid in state.order
                        if str(uid) != counterpart
                    )
                    or WAIT,
                )
            )
        if rule == REBEL_BASE_CAPTURE:
            fields.append(
                Field(
                    "overrun_base",
                    "Which actual unattended base is overrun?",
                    tuple((base.id, base.name) for base, _ in overrun_bases.values()) or WAIT,
                )
            )
            selected = overrun_bases.get(values.get("overrun_base", ("",))[0])
            foes = []
            held = []
            if selected is not None:
                base, parked = selected
                held = [
                    (frame.frame_instance, PilotSheet.model_validate_json(frame.frame_json).frame)
                    for frame in parked
                ]
                for pilot in world["pilots"]:
                    try:
                        body = overrun_attacker(state, pilot["id"], base)
                    except ValueError:
                        continue
                    foes.append((body.id, body.name))
            fields += [
                Field(
                    "overrun_rebel", "Which original Rebel leads the takeover?", tuple(foes) or WAIT
                ),
                Field(
                    "overrun_frame", "Which original parked Frame is seized?", tuple(held) or WAIT
                ),
            ]
        if rule == REBEL_SIEGE:
            fields.append(
                Field(
                    "siege_base",
                    "Which operational base is the Cadre occupying?",
                    tuple((site.id, site.name) for site in theft_bases.values()) or WAIT,
                )
            )
            fields.append(
                Field(
                    "siege_target",
                    "Who are the original Rebels trying to kill?",
                    (("ace", "The original Ace"), ("handler", "The original Handler")),
                    0,
                    required=False,
                )
            )
            if siege_seed:
                if siege_groups:
                    fields.append(
                        Field(
                            "siege_faction", "Active group for the three new Rebels", siege_groups
                        )
                    )
                else:
                    fields.extend(
                        (
                            Field("siege_group_name", "Name the new Rebel group"),
                            Field(
                                "siege_group_site",
                                "Where does the new group have influence?",
                                options(regional_locations),
                            ),
                        )
                    )
                for i in range(1, 4):
                    fields.extend(
                        (
                            Field(f"siege_{i}_name", f"Name of Rebel {i}"),
                            Field(
                                f"siege_{i}_controller",
                                f"Controller of Rebel {i}",
                                siege_controllers or WAIT,
                            ),
                            Field(f"siege_{i}_frame", f"Frame of Rebel {i}"),
                            Field(
                                f"siege_{i}_asset",
                                f"Operating Frame Asset of Rebel {i}",
                                paragraph=True,
                            ),
                        )
                    )
        if rule == FOUNDATION_ATTACK:
            fields.extend(
                (
                    Field(
                        "attacked_base",
                        "Which original person or base is targeted?",
                        tuple((site.id, site.name) for site in theft_bases.values())
                        + tuple(foundation_labels)
                        or WAIT,
                    ),
                    Field(
                        "foundation_pilot",
                        "Which original Foundation Pilot is sent?",
                        tuple(foundation_pilots) or WAIT,
                    ),
                )
            )
        if rule == REBEL_FRAME_THEFT:
            fields.append(
                Field(
                    "theft_base",
                    "Which actual base does the Rebel enter?",
                    tuple((site.id, site.name) for site in theft_bases.values()) or WAIT,
                )
            )
            selected_site = theft_bases.get(values.get("theft_base", ("",))[0])
            eligible_thieves = []
            if selected_site is not None:
                for pilot in world["pilots"]:
                    try:
                        thief = theft_actor(state, pilot["id"], selected_site.cell)
                    except ValueError:
                        continue
                    eligible_thieves.append((thief.id, thief.name))
            fields.append(
                Field(
                    "frame_thief",
                    "Which original Rebel is on foot here?",
                    tuple(eligible_thieves) or WAIT,
                )
            )
        if rule == REBEL_BOND_ATTACK:
            assert state.world is not None
            fields += [
                Field(
                    "betrayal_bond",
                    "Which original NPC Bond is a secret Rebel?",
                    tuple(
                        (x.id, x.name)
                        for x in state.world.npcs
                        if x.alive
                        and x.source_kind is None
                        and x.controller != handler
                        and x.captive_of is None
                        and "director" not in x.jobs
                        and original_bonds(state, x)
                    )
                    or WAIT,
                ),
                Field(
                    "betrayal_faction",
                    "Which Rebel Group do they serve?",
                    options([x for x in world["factions"] if x["kind"] == "rebel" and x["active"]]),
                ),
            ]
        if rule == REBEL_DEFECTION:
            assert state.world is not None
            group = values.get("defection_faction", ("",))[0]
            fields += [
                Field(
                    "defection_npc",
                    "Which actual NPC Bond is contacted?",
                    tuple(
                        (x.id, x.name)
                        for x in state.world.npcs
                        if x.alive and x.captive_of is None and original_bonds(state, x)
                    )
                    or WAIT,
                ),
                Field(
                    "defection_faction",
                    "Which active Rebel Group contacts the NPC?",
                    options([x for x in world["factions"] if x["kind"] == "rebel" and x["active"]]),
                ),
                Field(
                    "defection_contact",
                    "Which current member receives a report if the NPC defects?",
                    options(
                        [
                            x
                            for x in world["npcs"]
                            if x["alive"] and x["captive_of"] is None and x["faction"] == group
                        ]
                    ),
                ),
            ]
        if rule == "strain.rebellion.high.5.2":
            fields.append(Field("backstory_tag", "Your backstory-based Handler Tag"))
            fields.append(
                Field(
                    "backstory_observers",
                    "Girls who actually observed this Tag",
                    tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order),
                    0,
                    len(state.order),
                    required=False,
                )
            )
        if rift:
            fields.append(
                Field(
                    "arrival",
                    "What emerges from the open sky?",
                    (
                        ("gorgon", "Gorgon"),
                        ("harpy", "Harpy"),
                    ),
                )
            )
        rift_harpy = rift and values.get("arrival") == ("harpy",)
        if rule == "strain.rebellion.low.2.2":
            fields.append(
                Field(
                    "target",
                    "Actual base where the contraband is found",
                    options(
                        [
                            x
                            for x in world["locations"]
                            if x["kind"] == "base"
                            and in_responsibility(state, (x["cell"][0], x["cell"][1]))
                            and x["allegiance"] == "foundation"
                            and x["condition"] != "destroyed"
                        ]
                    ),
                )
            )
        elif rift_harpy:
            cells = tuple(
                x for x in squares(world["board"]) if in_responsibility(state, coordinates(x[0]))
            )
            fields += [
                Field("harpy_name", "Name of the arriving Harpy"),
                Field("harpy_frame", "Her actual Frame"),
                Field("girl_component", "Girl Asset"),
                Field("frame_component", "Frame Asset"),
                Field("cell", "Where does she emerge?", cells or WAIT),
                Field(
                    "revealed", "Has the Cadre seen her?", (("yes", "Yes"), ("no", "Keep private"))
                ),
            ]
        elif spawned or rift:
            if berserk:
                fields.append(
                    Field(
                        "berserk_owner",
                        "Which original Frame goes berserk on activation?",
                        tuple(
                            (
                                x.entity,
                                state.sheets[x.entity].callsign
                                + " · "
                                + state.sheets[x.entity].frame,
                            )
                            for x in berserk_frames(state)
                        )
                        or WAIT,
                    )
                )
            classes = (
                ("benevolent", "erratic")
                if disguise
                else ("dormant", "erratic", "benevolent", "aggressive", "directed", "sprite")
                if rift
                else ("directed",)
                if orbital or rule.endswith("1.1")
                else ("dormant", "erratic")
                if rule.endswith("2.1")
                else ("aggressive",)
                if rule.endswith("4.1")
                else ("sprite",)
            )
            selected_class = values.get("class", classes)[0]
            fields.append(
                Field("class", "Printed Gorgon Class", tuple((x, x.title()) for x in classes))
            )
            inherited = selected_class == "sprite"
            if inherited:
                fields.append(
                    Field(
                        "leader",
                        "Which actual Gorgon does the Sprite follow?",
                        options(
                            [
                                x
                                for x in world["gorgons"]
                                if x["alive"] and x["gorgon_class"] != "sprite"
                            ]
                        ),
                    )
                )
                leader = gorgons.get(values.get("leader", ("",))[0])
                types = leader["types"] if leader else []
                fields.append(
                    Field(
                        "type", "Inherited Type", (("inherit", "Use the selected leader's Types"),)
                    )
                )
            elif disguise:
                fields.append(
                    Field(
                        "mask",
                        "Which original NPC Bond is revealed?",
                        tuple((npc.id, npc.name) for npc in masks.values()) or WAIT,
                    )
                )
                types = ("doppleganger",)
            else:
                fields.append(Field("type", "Gorgon archetype Type", TYPES))
                types = values.get("type", ())
            pool = tuple(dict.fromkeys(label for kind in types for label in ASSETS.get(kind, ())))
            count = CLASS_ASSETS.get(selected_class, 1)
            fields.append(
                Field(
                    "assets",
                    "Choose its actual starting Assets",
                    tuple((x, x) for x in pool) or WAIT,
                    count if pool else 1,
                    count if pool else 1,
                )
            )
            assets = tuple((x, x) for x in values.get("assets", ()) if x in pool) or WAIT
            if selected_class == "directed":
                fields.append(Field("protected", "Which Asset protects the other Assets?", assets))
                fields.append(
                    Field(
                        "goal",
                        "Which location is below its orbit?"
                        if orbital
                        else "Which location is its goal?"
                        if rift
                        else "Which city is its goal?",
                        options(
                            [
                                x
                                for x in world["locations"]
                                if (orbital or rift or x["kind"] == "city")
                                and x["condition"] != "destroyed"
                                and in_responsibility(state, (x["cell"][0], x["cell"][1]))
                            ]
                        ),
                    )
                )
            fields += [
                Field(
                    "core", "Core-protecting Assets (one or two)", assets, 1, min(2, len(assets))
                ),
                Field("weakness", "What tactical weakness exposes its Core?", paragraph=True),
            ]
            if not disguise:
                fields.append(Field("name", "Name or identifying label"))
            cells = squares(world["board"])
            bases = [
                x["cell"]
                for x in world["locations"]
                if x["kind"] == "base"
                and x["condition"] != "destroyed"
                and in_responsibility(state, (x["cell"][0], x["cell"][1]))
            ]
            cities = [
                tuple(x["cell"])
                for x in world["locations"]
                if x["kind"] == "city"
                and x["condition"] != "destroyed"
                and in_responsibility(state, (x["cell"][0], x["cell"][1]))
            ]
            if rift:
                cells = tuple(x for x in cells if in_responsibility(state, coordinates(x[0])))
            elif selected_class == "directed":
                cells = tuple(x for x in cells if responsibility_edge(state, coordinates(x[0])))
            elif selected_class in ("dormant", "erratic"):
                cells = tuple(
                    x
                    for x in cells
                    if any(distance(coordinates(x[0]), cast(Any, base)) == 1 for base in bases)
                )
            elif selected_class == "aggressive":
                cells = tuple(x for x in cells if coordinates(x[0]) in cities)
            else:
                cells = tuple(x for x in cells if list(coordinates(x[0])) in bases)
            if not (orbital or disguise or berserk):
                fields.append(Field("cell", "Choose a source-legal map square", cells or WAIT))
            if selected_class == "aggressive" or (selected_class == "sprite" and not rift):
                selected_cell = values.get("cell", ("",))[0]
                if berserk:
                    owner = values.get("berserk_owner", (None,))[0]
                    placement = next((x for x in state.placements if x.actor.entity == owner), None)
                    if placement is not None and placement.frame_cell is not None:
                        selected_cell = f"{placement.frame_cell[0]},{placement.frame_cell[1]}"
                victims = [
                    x
                    for x in world["npcs"]
                    if x["alive"]
                    and category(state, ActorRef(kind="npc", entity=x["id"])) != "harpy"
                    and (
                        not berserk
                        or category(state, ActorRef(kind="npc", entity=x["id"])) == "npc"
                    )
                    and x["cell"] is not None
                    and f"{x['cell'][0]},{x['cell'][1]}" == selected_cell
                ]
                fields.append(
                    Field(
                        "victim",
                        "NPC killed on introduction"
                        if selected_class == "aggressive"
                        else "NPC the Sprite already captured",
                        options(victims),
                    )
                )
            if not berserk:
                fields.append(
                    Field(
                        "revealed",
                        "Has the Cadre seen this Gorgon?",
                        (("yes", "Yes"), ("no", "Keep private")),
                    )
                )
        elif rule == "strain.void.high.3.1":
            fields.append(
                Field(
                    "target",
                    "Which defeated Gorgon returns?",
                    options([x for x in world["gorgons"] if not x["alive"]]),
                )
            )
            target = gorgons.get(values.get("target", ("",))[0])
            fields.append(
                Field(
                    "type",
                    "Additional distinct Type",
                    tuple(x for x in TYPES if not target or x[0] not in target["types"]) or WAIT,
                )
            )
            fields.append(Field("new_assets", "Two new Asset names, one per line", paragraph=True))
            core = tuple((x["id"], x["name"]) for x in target["assets"]) if target else ()
            fields += [
                Field(
                    "core",
                    "New Core-protecting Assets",
                    core + (("new0", "First new Asset"), ("new1", "Second new Asset")),
                    1,
                    2,
                ),
                Field("weakness", "Describe its new Core weakness", paragraph=True),
            ]
        elif rule in (
            "strain.rebellion.low.1.1",
            "strain.rebellion.low.6.1",
            "strain.budget.high.3.2",
        ):
            fields.append(Field("name", "New faction name"))
            if rule == "strain.rebellion.low.1.1":
                fields.append(
                    Field("target", "Which city?", options(regional_locations, kind="city"))
                )
            elif rule == "strain.rebellion.low.6.1":
                occupied = {tuple(x["cell"]) for x in world["locations"]}
                fields += [
                    Field("base_name", "Rebel Base name"),
                    Field(
                        "cell",
                        "Choose its distant empty square",
                        tuple(
                            x
                            for x in squares(world["board"])
                            if coordinates(x[0]) not in occupied
                            and in_responsibility(state, coordinates(x[0]))
                        )
                        or WAIT,
                    ),
                ]
            else:
                fields.append(
                    Field(
                        "cells",
                        "Where does this political faction hold power?",
                        squares(world["board"]),
                        1,
                        25,
                    )
                )
        elif rule in ("strain.budget.low.5.1", "strain.budget.low.6.1"):
            fields.append(
                Field(
                    "visitor",
                    "Actual NPC higher-up or politician (introduce through /mission world first)",
                    options(
                        [
                            x
                            for x in world["npcs"]
                            if x["alive"] and x["cell"] is not None and "director" not in x["jobs"]
                        ]
                    ),
                )
            )
        elif rule == "strain.budget.high.6.1":
            fields.extend(
                (
                    Field(
                        "storage_owner",
                        "Original current ordinary Frame owner",
                        tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order),
                    ),
                    Field(
                        "storage_base",
                        "Surviving Foundation base",
                        options(
                            [
                                x
                                for x in world["locations"]
                                if x["kind"] == "base"
                                and x["allegiance"] == "foundation"
                                and x["condition"] != "destroyed"
                            ]
                        ),
                    ),
                    Field(
                        "storage_superior",
                        "Actual claimed ordinary higher-up",
                        options(
                            [
                                x
                                for x in world["npcs"]
                                if x["alive"]
                                and x["controller"] is not None
                                and "director" not in x["jobs"]
                            ]
                        ),
                    ),
                )
            )
        elif rule == "strain.budget.high.4.1":
            fields.extend(
                (
                    Field(
                        "fighters",
                        "Which two Girls will fight?",
                        tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order),
                        2,
                        2,
                    ),
                    Field(
                        "fight_channel",
                        "Actual Play scene for the televised fight",
                        channels or WAIT,
                    ),
                )
            )
        elif rule == "strain.rebellion.low.5.2":
            fields.append(
                Field(
                    "contact_city",
                    "Which actual city is nearby?",
                    options([x for x in world["locations"] if x["kind"] == "city"]),
                )
            )
        elif rule == "strain.budget.low.2.2":
            fields.append(
                Field("assets", "Two secret Cadre Assets", tuple(asset_labels.items()), 2, 2)
            )
        elif rule == "strain.budget.low.4.1":
            fields += [
                Field(
                    "mission",
                    "Which completed past mission?",
                    tuple((x["id"], x["objective"][:100]) for x in past_missions),
                ),
                Field("site", "Where did that mission take place?", options(world["locations"])),
                Field(
                    "cleanup_mode",
                    "How will cleanup be played?",
                    (
                        ("scene", "Play a cleanup scene"),
                        ("exposure", "Cleanup occurred: one random Girl gains Void"),
                    ),
                ),
            ]
        elif rule == "strain.budget.low.3.1":
            fields.append(
                Field(
                    "subjects",
                    "Which Girls are required for Observation?",
                    tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order),
                    1,
                    min(2, len(state.order)),
                )
            )
            fields.extend(
                Field(
                    "hide:" + uid,
                    state.sheets[uid].callsign + " — suspect hiding?",
                    (("yes", "Yes, record that suspicion"), ("no", "No hiding suspicion")),
                )
                for uid in values.get("subjects", ())
            )
        elif rule == "strain.budget.low.3.2":
            fields.append(Field("missing_resource", "What resource is missing?"))
        elif rule == "strain.budget.low.5.2":
            for uid in state.order:
                fields.append(
                    Field(
                        "room:" + str(uid),
                        state.sheets[str(uid)].callsign + " — assign a room",
                        tuple((str(i), "Room " + str(i + 1)) for i in range(len(state.order) // 2)),
                    )
                )
        elif rule == "strain.budget.low.6.2":
            fields += [
                Field(
                    "target",
                    "Which actual NPC Bond is fired?",
                    options([x for x in world["npcs"] if x["alive"] and x["bonds"]]),
                ),
                Field(
                    "jobs",
                    "Choose their changed NPC playbooks",
                    tuple((x, x.replace("_", " ").title()) for x in NPC_JOBS),
                    1,
                    len(NPC_JOBS),
                ),
            ]
        elif rule == "strain.budget.high.4.2":
            fields += [
                Field(
                    "candidate",
                    "Actual NPC to assess",
                    options([x for x in world["npcs"] if x["alive"]]),
                ),
                Field(
                    "assessor",
                    "Girl assigned to assess",
                    tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order),
                ),
            ]
        elif rule == "strain.budget.high.1.1":
            fields.append(
                Field(
                    "director",
                    "Director played by a different human",
                    options(
                        [
                            x
                            for x in world["npcs"]
                            if x["alive"] and "director" in x["jobs"] and x["controller"] != handler
                        ]
                    ),
                )
            )
        elif rule == "strain.budget.low.2.1":
            fields += [
                Field(
                    "patron",
                    "Existing political patron",
                    options([x for x in world["npcs"] if x["alive"] and "patron" in x["jobs"]]),
                ),
                Field(
                    "function",
                    "The actual function",
                    tuple((x, x.title()) for x in ("auction", "fundraiser", "ball", "orgy")),
                ),
            ]
        elif rule == "strain.budget.low.1.2":
            fields += [
                Field(
                    "girl",
                    "Girl the patron takes a liking to",
                    tuple((str(uid), state.sheets[str(uid)].callsign) for uid in state.order),
                ),
                Field(
                    "patron",
                    "Existing rich patron",
                    options([x for x in world["npcs"] if x["alive"] and "patron" in x["jobs"]]),
                ),
            ]
        elif rule in ("strain.budget.high.2.2", "strain.budget.low.1.1"):
            fields += [
                Field(
                    "tag:" + str(uid),
                    (
                        "Public perception — "
                        if rule == "strain.budget.low.1.1"
                        else "Shortage Tag — "
                    )
                    + ("Handler" if uid == state.handler else state.sheets[str(uid)].callsign),
                )
                for uid in (
                    state.order
                    if rule == "strain.budget.low.1.1"
                    else (state.handler, *state.order)
                )
            ]
        elif rule in ("strain.budget.high.5.1", REBEL_PROTEST):
            fields.append(
                Field(
                    "target",
                    "Which city does the protest overtake?"
                    if rule == REBEL_PROTEST
                    else "Which surviving city falls into anarchy?",
                    options(
                        [
                            x
                            for x in world["locations"]
                            if x["kind"] == "city"
                            and x["condition"] != "destroyed"
                            and in_responsibility(state, (x["cell"][0], x["cell"][1]))
                        ]
                    ),
                )
            )
            if rule == REBEL_PROTEST:
                fields.append(
                    Field(
                        "faction",
                        "Which active Rebel faction leads the protest?",
                        options(
                            [x for x in world["factions"] if x["kind"] == "rebel" and x["active"]]
                        ),
                    )
                )
        fields.append(
            Field("account", "Describe the actual event and consequences", paragraph=True)
        )
        return fields

    def apply(actor: GuildViewer, key: str, values: dict[str, Any]) -> str:
        payload: dict[str, Any] = {"rule_id": rule, "account": values["account"]}
        if rule == REBEL_STRAFE:
            payload.update(target=values["strafe_base"][0], victim=values["strafe_pilot"][0])
        if rule == NPC_INTEREST:
            payload.update(
                target=values["interest_npc"][0],
                victim=values["interest_girl"][0],
                interest_timing=values["interest_timing"][0],
                interest_manifestation=values.get("interest_manifestation", (None,))[0],
            )
        if rule == SPRITE_ESCORT:
            payload["sprite_escort"] = SpriteEscortDesign(
                name=values["sprite_name"],
                assets=(values["sprite_first"], values["sprite_second"]),
                weakness=values["sprite_weakness"],
                both_assets=values["sprite_core"] == ("both",),
            )
        if rule == BENEVOLENT_CONTACT:
            payload.update(
                target=values["contact_gorgon"][0],
                victim=values["contact_girl"][0],
                contact_channel=int(values["contact_channel"][0]),
                contact_play=values["contact_play"][0],
            )
        if rule == CULT_OCCUPATION:
            selected = values["cult_harpy"][0]
            site_id = values["cult_site"][0]
            assert state.world is not None
            site = next((x for x in state.world.locations if x.id == site_id), None)
            if site is None:
                raise WorkflowError("Choose the actual location the cult occupies.")
            payload.update(
                target=site.id,
                faction=Faction(
                    id=stable(identity, "cult"),
                    name=values["cult_name"],
                    kind="cult",
                    cells=(site.cell,),
                ),
                cult_harpy=selected,
            )
            if selected == new_cult_actor:
                payload["new_cult_harpy"] = AdversaryPilot(
                    id=selected,
                    kind="harpy",
                    girl="HARPY",
                    controller=handler,
                    cell=site.cell,
                    name=values["harpy_name"],
                    frame=values["harpy_frame"],
                    assets=(
                        Asset(
                            id=stable(identity, "cult girl component"),
                            family="girl",
                            name=values["girl_component"],
                            description=values["girl_component"],
                        ),
                        Asset(
                            id=stable(identity, "cult frame component"),
                            family="frame",
                            name=values["frame_component"],
                            description=values["frame_component"],
                        ),
                    ),
                )
        if rule == HARPY_RAID:
            selected = values["harpy"][0]
            site_id = values["raid_base"][0]
            payload.update(
                target=selected,
                victim=values["obsession"][0],
                raid_base=site_id,
            )
            if selected == new_raid_actor:
                assert state.world is not None
                base = next((x for x in state.world.locations if x.id == site_id), None)
                if base is None:
                    raise WorkflowError("Choose the actual occupied base.")
                payload["new_raid_harpy"] = AdversaryPilot(
                    id=selected,
                    kind="harpy",
                    girl="HARPY",
                    controller=handler,
                    cell=base.cell,
                    name=values["harpy_name"],
                    frame=values["harpy_frame"],
                    assets=(
                        Asset(
                            id=stable(identity, "raid girl component"),
                            family="girl",
                            name=values["girl_component"],
                            description=values["girl_component"],
                        ),
                        Asset(
                            id=stable(identity, "raid frame component"),
                            family="frame",
                            name=values["frame_component"],
                            description=values["frame_component"],
                        ),
                    ),
                )
        if rule == VOID_SIGNAL:
            payload["target"] = values["signal"][0]
        if rule == PUBLIC_APPEARANCE:
            payload["target"] = values["appearance_city"][0]
        if rule in CIVIC_DIRECTIVES or rule in (PILOT_FEARS, CADRE_LEAK, BUDGET_HEARING):
            payload["target"] = values["civic_director"][0]
            if rule == CIVIC_PROTEST:
                payload["protest_city"] = values["protest_city"][0]
        if rule == BUDGET_HEARING:
            payload["victim"] = values["hearing_girl"][0]
        if rule == BUNK_HARPY:
            payload["target"] = values["bunk_harpy"][0]
        if rule == CADRE_LEAK:
            if any(x not in parties_by_token for x in values["parties"]):
                raise WorkflowError("Recover the actual original parties of this incident")
            payload["leak_parties"] = tuple(parties_by_token[x] for x in values["parties"])
            payload["leak_report"] = values["leak_report"]
        if rule == VOID_REVELATION:
            payload.update(
                revelation_play=values["revelation"][0],
                revelation_channel=int(values["revelation_scene"][0]),
            )
        if rule in (REBEL_ESCAPE_OFFER, REBEL_TAUNT, REBEL_VOICE):
            payload["target"] = values["rebel_handler"][0]
        if rule in (REBEL_AMBUSH, REBEL_HUNT):
            payload["target"] = values["ambusher"][0]
        if rule == REBEL_HUNT:
            payload["victim"] = values["hunt_victim"][0]
        if rule == REBEL_BASE_CAPTURE:
            payload.update(
                target=values["overrun_base"][0],
                victim=values["overrun_rebel"][0],
                captured_frame=values["overrun_frame"][0],
            )
        if rule == REBEL_SIEGE:
            base_id = values["siege_base"][0]
            payload["target"] = base_id
            if values.get("siege_target"):
                payload["victim"] = values["siege_target"][0]
            if siege_seed:
                if base_id not in theft_bases:
                    raise WorkflowError("Choose the actual base and active Rebel group")
                cell = theft_bases[base_id].cell
                if siege_groups:
                    faction = values["siege_faction"][0]
                else:
                    assert state.world is not None
                    territory = next(
                        x for x in state.world.locations if x.id == values["siege_group_site"][0]
                    )
                    faction = stable(identity, "new siege faction")
                    payload["faction"] = Faction(
                        id=faction,
                        name=values["siege_group_name"],
                        kind="rebel",
                        cells=(territory.cell,),
                    )
                payload["siege_recruits"] = tuple(
                    AdversaryPilot(
                        id=stable(identity, f"new siege Pilot {i}"),
                        kind="rebel",
                        name=values[f"siege_{i}_name"],
                        controller=int(values[f"siege_{i}_controller"][0]),
                        girl="MOCKINGBIRD",
                        frame=values[f"siege_{i}_frame"],
                        cell=cell,
                        faction=faction,
                        assets=(
                            Asset(
                                id=stable(identity, f"new siege Frame Asset {i}"),
                                name=values[f"siege_{i}_asset"],
                                description=values[f"siege_{i}_asset"],
                                family="frame",
                            ),
                        ),
                    )
                    for i in range(1, 4)
                )
        if rule == FOUNDATION_ATTACK:
            target = values["attacked_base"][0]
            if target in foundation_people:
                mode, target = foundation_people[target]
                payload["foundation_person"] = mode
            payload.update(target=target, victim=values["foundation_pilot"][0])
        if rule == REBEL_FRAME_THEFT:
            payload.update(target=values["theft_base"][0], victim=values["frame_thief"][0])
        if rule == REBEL_BOND_ATTACK:
            payload.update(
                target=values["betrayal_bond"][0], faction_id=values["betrayal_faction"][0]
            )
        if rule == REBEL_DEFECTION:
            payload.update(
                target=values["defection_npc"][0],
                faction_id=values["defection_faction"][0],
                defection_recipient=values["defection_contact"][0],
            )
        if rule == "strain.rebellion.high.5.2":
            payload["tags"] = (dict(owner=handler, label=values["backstory_tag"]),)
            payload["backstory_observers"] = tuple(
                int(x) for x in values.get("backstory_observers", ())
            )
        if rule == "strain.rebellion.low.2.2":
            payload["target"] = values["target"][0]
        elif rift and values.get("arrival") == ("harpy",):
            payload["rift_harpy"] = AdversaryPilot(
                id=stable(identity, "rift Harpy"),
                kind="harpy",
                girl="HARPY",
                controller=handler,
                cell=coordinates(values["cell"][0]),
                name=values["harpy_name"],
                frame=values["harpy_frame"],
                revealed=values["revealed"][0] == "yes",
                assets=(
                    Asset(
                        id=stable(identity, "girl"),
                        name=values["girl_component"],
                        family="girl",
                        description=values["girl_component"],
                    ),
                    Asset(
                        id=stable(identity, "frame"),
                        name=values["frame_component"],
                        family="frame",
                        description=values["frame_component"],
                    ),
                ),
            )
        elif spawned or rift:
            selected_class = values["class"][0]
            types = (
                ("doppleganger",)
                if disguise
                else tuple(gorgons[values["leader"][0]]["types"])
                if selected_class == "sprite"
                else tuple(values["type"])
            )
            assets = tuple(
                Asset(
                    id=stable(identity, "asset:" + name),
                    name=name,
                    description=name,
                    family="gorgon",
                )
                for name in values["assets"]
            )
            asset_ids = {x.name: x.id for x in assets}
            setup: dict[str, Any] = {}
            if selected_class == "directed":
                setup.update(
                    goal=Goal(kind="location", entity_id=values["goal"][0]),
                    protected_asset=asset_ids[values["protected"][0]],
                )
            if selected_class == "sprite":
                setup["follows"] = values["leader"][0]
            mask = masks.get(values["mask"][0]) if disguise else None
            if disguise and mask is None:
                raise WorkflowError("Recover a bonded NPC under the Handler's actual control.")
            if mask is not None:
                payload["target"] = mask.id
            if berserk:
                payload["target"] = values["berserk_owner"][0]
            payload["gorgon"] = Gorgon(
                id=mask.id if mask else stable(identity, "gorgon"),
                name=mask.name if mask else values["name"],
                gorgon_class=cast(Any, selected_class),
                types=cast(Any, types),
                assets=assets,
                cell=mask.cell
                if mask
                else None
                if orbital or berserk
                else coordinates(values["cell"][0]),
                core_plan=CorePlan(
                    assets=tuple(asset_ids[x] for x in values["core"]), weakness=values["weakness"]
                ),
                revealed=not berserk and values["revealed"][0] == "yes",
                **setup,
            )
            if "victim" in values:
                payload["victim"] = values["victim"][0]
        elif rule == "strain.void.high.3.1":
            names = [x.strip() for x in values["new_assets"].splitlines()]
            if len(names) != 2 or any(not x for x in names):
                raise WorkflowError("Name exactly two new Assets.")
            new_assets = tuple(
                Asset(
                    id=stable(identity, "new" + str(i)),
                    name=name,
                    description=name,
                    family="gorgon",
                )
                for i, name in enumerate(names)
            )
            core = tuple(
                new_assets[int(x[-1])].id if x in ("new0", "new1") else x for x in values["core"]
            )
            payload.update(
                target=values["target"][0],
                new_assets=new_assets,
                new_type=values["type"][0],
                core_plan=CorePlan(assets=core, weakness=values["weakness"]),
            )
        elif rule in (
            "strain.rebellion.low.1.1",
            "strain.rebellion.low.6.1",
            "strain.budget.high.3.2",
        ):
            kind = "political" if rule == "strain.budget.high.3.2" else "rebel"
            if rule == "strain.rebellion.low.1.1":
                target = (
                    next(x for x in state.world.locations if x.id == values["target"][0])
                    if state.world
                    else None
                )
                if target is None:
                    raise WorkflowError("Choose the actual city.")
                cells: tuple[tuple[int, int], ...] = (target.cell,)
                payload["target"] = target.id
            elif rule == "strain.rebellion.low.6.1":
                cell = coordinates(values["cell"][0])
                payload["location"] = Location(
                    id=stable(identity, "base"),
                    name=values["base_name"],
                    kind="base",
                    allegiance="rebel",
                    cell=cell,
                )
                cells = (cell,)
            else:
                cells = tuple(coordinates(x) for x in values["cells"])
            payload["faction"] = Faction(
                id=stable(identity, "faction"),
                name=values["name"],
                kind=cast(Any, kind),
                cells=cells,
            )
        elif rule == "strain.budget.low.5.2":
            grouped: dict[str, list[int]] = {}
            for uid in state.order:
                grouped.setdefault(values["room:" + str(uid)][0], []).append(uid)
            payload["rooms"] = tuple(tuple(x) for x in grouped.values())
        elif rule == "strain.budget.low.6.2":
            payload.update(target=values["target"][0], npc_jobs=tuple(values["jobs"]))
        elif rule in ("strain.budget.low.5.1", "strain.budget.low.6.1"):
            payload["target"] = values["visitor"][0]
        elif rule == "strain.budget.high.6.1":
            payload.update(
                storage_owner=int(values["storage_owner"][0]),
                target=values["storage_base"][0],
                victim=values["storage_superior"][0],
            )
        elif rule == "strain.budget.high.4.1":
            channel = int(values["fight_channel"][0])
            with service.store.engine.connect() as c:
                source_scene = service.game.scene(c, channel)
            payload.update(
                target=source_scene["id"],
                fighters=tuple(int(x) for x in values["fighters"]),
                fight_channel=channel,
            )
        elif rule == "strain.rebellion.low.5.2":
            payload["target"] = values["contact_city"][0]
        elif rule == "strain.budget.low.2.2":
            if any(x not in asset_pins for x in values["assets"]):
                raise WorkflowError("Reopen the original actual Cadre Asset choices")
            payload["planned_assets"] = tuple(asset_pins[x] for x in values["assets"])
        elif rule == "strain.budget.low.4.1":
            payload.update(
                target=values["site"][0],
                victim=values["mission"][0],
                cleanup_mode=values["cleanup_mode"][0],
            )
        elif rule == "strain.budget.low.3.1":
            payload["scientific_demand"] = Demand(
                subjects=tuple(int(x) for x in values["subjects"]),
                hiding={uid: values["hide:" + uid][0] == "yes" for uid in values["subjects"]},
            )
        elif rule == "strain.budget.low.3.2":
            payload["missing_resource"] = values["missing_resource"]
        elif rule == "strain.budget.high.4.2":
            payload.update(target=values["candidate"][0], victim=values["assessor"][0])
        elif rule == "strain.budget.high.1.1":
            payload["target"] = values["director"][0]
        elif rule == "strain.budget.low.2.1":
            payload.update(target=values["patron"][0], function_kind=values["function"][0])
        elif rule == "strain.budget.low.1.2":
            payload.update(target=values["girl"][0], victim=values["patron"][0])
        elif rule in ("strain.budget.high.2.2", "strain.budget.low.1.1"):
            payload["tags"] = tuple(
                TagChoice(owner=uid, label=values["tag:" + str(uid)])
                for uid in (
                    state.order if rule == "strain.budget.low.1.1" else (handler, *state.order)
                )
            )
        elif rule in ("strain.budget.high.5.1", REBEL_PROTEST):
            payload["target"] = values["target"][0]
            if rule == REBEL_PROTEST:
                payload["faction_id"] = values["faction"][0]
        service.apply(
            actor,
            key,
            identity,
            data["revision"],
            data["game_revision"],
            Choice(**payload),
        )
        if rule == "strain.budget.low.3.2":
            saved = service.get(actor, identity)
            outcome = saved["supply_outcome"]
            return (
                "Missing supply assigned to "
                + str(outcome["recipient"])
                + ": "
                + str(outcome["resource"])
                + "."
            )
        if rule == "strain.rebellion.low.1.2":
            return (
                "Control slip recorded. The next actual Girl Disobey Orders roll "
                "gets +2, separate from Heat and later Tags. No recipient was chosen."
            )
        if rule == "strain.rebellion.low.2.2":
            return "Private find saved. The recipient can review it in their requests inbox."
        if rule == REBEL_ESCAPE_OFFER:
            return "The private offer is pending with the original rebel controller."
        if rule == REBEL_TAUNT:
            return "The original Rebel controller can transmit the taunt from the private Inbox."
        if rule == REBEL_VOICE:
            return "The original Rebel controller can finish the voice from their private Inbox."
        if rule in CIVIC_DIRECTIVES:
            return "The original Director's order is pending in their private Inbox."
        if rule == VOID_SIGNAL:
            return "The original recipient can finish the Void change in their private Inbox."
        if rule == PILOT_FEARS:
            return "The original fictional Director can issue the demand in their private Inbox."
        if rule == BUDGET_HEARING:
            return "The Director can serve the accusation privately."
        if rule == BUNK_HARPY:
            return "The appearance is available to its original Harpy controller."
        if rule == BERSERK_FRAME:
            return "The threat is tied to the original Frame's next activation."
        if rule == REBEL_AMBUSH:
            return "The original attack is pending for the next dispatched mission."
        if rule == REBEL_HUNT:
            return "The original Rebel will pursue this Girl on future missions."
        if rule == REBEL_SIEGE:
            return "Each original Rebel can open their attack from their private Inbox."
        if rule == FOUNDATION_ATTACK:
            return "The original Foundation Pilot can make the attack from their private Inbox."
        if rule == REBEL_BASE_CAPTURE:
            return "The base fell. Prisoners are free and the parked Frame is in Rebel custody."
        if rule == REBEL_BOND_ATTACK:
            return "The original NPC's attack is pending in the private Inbox."
        if rule == REBEL_FRAME_THEFT:
            return "The original Rebel can attempt the theft in the source scene."
        if rule == PUBLIC_APPEARANCE:
            return "The original Cadre can record attendance from their private Inbox."
        if rule == HARPY_RAID:
            return "The original Harpy's controller can confirm the real attack in the Inbox."
        if rule == CADRE_LEAK:
            return "The original incident is pending. Reopen its private review."
        if rule == NPC_INTEREST:
            return "The original discovery and Void gain can be completed from the private Inbox."
        if rule == REBEL_STRAFE:
            return (
                "The original Rebel controller can make the physical pass from the private Inbox."
            )
        return "Event effects committed once. Reopen Off-Duty for remaining work."

    instructions = (
        "Review "
        + rule
        + ". "
        + (
            "The next actual Girl refusal gets +2; you do not choose its recipient. "
            if rule == "strain.rebellion.low.1.2"
            else ""
        )
        + (
            "The saved rift requires an arrival now and on the next "
            f"{data['rift_duration']} Strain rolls. "
            if rift and data["rift_duration"] is not None
            else "This saved Strain roll requires one rift arrival. "
            if rift
            else ""
        )
        + "Confirming applies its named world and character consequences. "
        "If no legal target exists, recover its actual world setup and reopen."
    )
    return build, apply, instructions
