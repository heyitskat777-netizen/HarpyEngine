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
from girlframe.engine.m3_gorgon_catalog import ASSETS
from girlframe.engine.m3_scientific_observation import Demand
from girlframe.engine.m3_strain_effects import Choice, TagChoice
from girlframe.engine.m3_world import CLASS_ASSETS, distance
from girlframe.engine.m3_world_state import (
    NPC_JOBS,
    Asset,
    CorePlan,
    Faction,
    Goal,
    Gorgon,
    Location,
)
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

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
    if data["state"] != "pending":
        await reply(
            interaction,
            "This effect is already applied. Reopen Off-Duty for current required work.",
        )
        return
    if not data["supported"]:
        await reply(
            interaction,
            "This event awaits its specific rules support. Its saved result remains required work.",
        )
        return
    snapshot = await asyncio.to_thread(
        WorldService(service.strain.missions).get, viewer, private=True
    )
    world = snapshot["world"]
    if world is None:
        await reply(
            interaction,
            "Initialize the map with /mission world first, then reopen this event.",
        )
        return
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
    from girlframe.engine.m3_promotional_opportunity import in_responsibility, responsibility_edge

    regional_locations = [
        x for x in world["locations"] if in_responsibility(state, (x["cell"][0], x["cell"][1]))
    ]
    if rule in ("strain.budget.low.1.2", "strain.budget.low.2.1") and not any(
        x["alive"] and "patron" in x["jobs"] for x in world["npcs"]
    ):
        await reply(
            interaction,
            "Introduce the patron through /mission world, then reopen this result.",
        )
        return
    spawned = rule in {
        "strain.void.low.1.1",
        "strain.void.low.2.1",
        "strain.void.low.4.1",
        "strain.void.low.5.1",
    }
    gorgons = {x["id"]: x for x in world["gorgons"]}
    past_missions = []
    if rule == "strain.budget.low.4.1":
        past_missions = [
            x
            for x in await asyncio.to_thread(service.strain.missions.list, viewer)
            if x["phase"] == "complete"
        ]
        if not past_missions:
            await reply(interaction, "This cleanup needs an actual completed past mission first.")
            return

    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_battle import category
    from girlframe.engine.m3_budget_sabotage import Pin

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
        elif spawned:
            classes = (
                ("directed",)
                if rule.endswith("1.1")
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
                        "Which city is its goal?",
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
            fields += [
                Field(
                    "core", "Core-protecting Assets (one or two)", assets, 1, min(2, len(assets))
                ),
                Field("weakness", "What tactical weakness exposes its Core?", paragraph=True),
                Field("name", "Name or identifying label"),
            ]
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
            if selected_class == "directed":
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
            fields.append(Field("cell", "Choose a source-legal map square", cells or WAIT))
            if selected_class in ("aggressive", "sprite"):
                selected_cell = values.get("cell", ("",))[0]
                victims = [
                    x
                    for x in world["npcs"]
                    if x["alive"]
                    and category(state, ActorRef(kind="npc", entity=x["id"])) != "harpy"
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
                        ((str(interaction.channel_id), "Use this Play scene"),),
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
        elif rule == "strain.budget.high.5.1":
            fields.append(
                Field(
                    "target",
                    "Which surviving city falls into anarchy?",
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
        fields.append(
            Field("account", "Describe the actual event and consequences", paragraph=True)
        )
        return fields

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        payload: dict[str, Any] = {"rule_id": rule, "account": values["account"]}
        if rule == "strain.rebellion.high.5.2":
            payload["tags"] = (dict(owner=handler, label=values["backstory_tag"]),)
            payload["backstory_observers"] = tuple(
                int(x) for x in values.get("backstory_observers", ())
            )
        if rule == "strain.rebellion.low.2.2":
            payload["target"] = values["target"][0]
        elif spawned:
            selected_class = values["class"][0]
            types = (
                tuple(gorgons[values["leader"][0]]["types"])
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
            payload["gorgon"] = Gorgon(
                id=stable(identity, "gorgon"),
                name=values["name"],
                gorgon_class=cast(Any, selected_class),
                types=cast(Any, types),
                assets=assets,
                cell=coordinates(values["cell"][0]),
                core_plan=CorePlan(
                    assets=tuple(asset_ids[x] for x in values["core"]), weakness=values["weakness"]
                ),
                revealed=values["revealed"][0] == "yes",
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
        elif rule == "strain.budget.high.5.1":
            payload["target"] = values["target"][0]
        await asyncio.to_thread(
            service.apply,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            Choice(**payload),
        )
        if rule == "strain.budget.low.3.2":
            saved = await asyncio.to_thread(service.get, viewer_from_interaction(current), identity)
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
        return "Event effects committed once. Reopen Off-Duty for remaining work."

    form = DependentForm(
        viewer.user_id,
        "Apply the saved Strain event",
        "Review "
        + rule
        + ". "
        + (
            "The next actual Girl refusal gets +2; you do not choose its recipient. "
            if rule == "strain.rebellion.low.1.2"
            else ""
        )
        + "Confirming applies its named world and character consequences. "
        "If no legal NPC/target exists, introduce it through /mission world, then reopen.",
        build,
        submit,
    )
    await reply(interaction, form.text(), form)
