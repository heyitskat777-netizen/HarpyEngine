"""Read-only campaign sheet review for its approved facilitator."""

from p2_scene import activity_facilitator

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_clone_am import copies
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m2_state import load_state, public_sheet
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.sheet_portrayal import SheetPortrayalService


def may_review(connection, game, viewer):
    return activity_facilitator(connection, game.store) == viewer.user_id


def pilot_record(sheet, state):
    public = public_sheet(sheet, state)
    return {
        "name": public["callsign"],
        "kind": "Pilot",
        "status": public.get("rank", "Active"),
        "girl": public["girl_playbook"],
        "frame": public["frame_playbook"],
        "frame_name": public.get("frame_name"),
        "frame_appearance": public.get("frame_appearance"),
        "description": public.get("appearance"),
        "heat": sheet.heat,
        "identities": [{"name": name} for name in public.get("identities", ())],
        "assets": public.get("assets", []),
    }


def cast_records(state, bindings):
    candidates = {}
    if state.world:
        candidates.update(
            (ActorRef(kind="npc", entity=npc.id), ("NPC", npc.name, npc.detail))
            for npc in state.world.npcs
        )
        candidates.update(
            (
                ActorRef(kind="external_pilot", entity=pilot.id),
                ("Harpy" if pilot.kind == "harpy" else "External Pilot", pilot.name, None),
            )
            for pilot in state.world.pilots
        )
        candidates.update(
            (ActorRef(kind="gorgon", entity=gorgon.id), ("Gorgon", gorgon.name, None))
            for gorgon in state.world.gorgons
        )
    candidates.update(
        (ActorRef(kind="external_pilot", entity=harpy.id), ("Harpy", harpy.name, None))
        for harpy in state.harpy_states
    )
    candidates.update(
        (ActorRef(kind="external_pilot", entity=core.id), ("JANUS Core", "JANUS Core", None))
        for core in state.janus_cores
    )
    candidates.update((copy.ref, ("AM copy", "AM copy", None)) for copy in copies(state))
    if handler := active_handler(state):
        context = next(
            (row for row in state.director_contexts if row.active and row.handler == state.handler),
            None,
        )
        candidates[
            handler.model_copy(update={"incarnation": context.id}) if context else handler
        ] = ("Handler", "Handler", None)

    for ref, (kind, name, description) in candidates.items():
        try:
            actor = resolve(
                state, ref, bindings, require_alive=False, require_current_profile=False
            )
        except ValueError:
            yield {"kind": kind, "name": name, "status": "Sheet unavailable"}
            continue
        native = SheetPortrayalService.native_record(state, actor) or {}
        yield {
            "kind": "Harpy" if native.get("kind") == "harpy" else kind,
            "name": actor.label,
            "status": "Active" if actor.alive else "Inactive",
            "description": description,
            "girl": actor.girl,
            "frame": actor.frame,
            "jobs": actor.jobs,
            "heat": actor.heat,
            "gorgon_class": native.get("gorgon_class"),
            "types": native.get("types", []),
            "core_exposed": actor.core_exposed,
            "core_weakness": native.get("core_weakness"),
            "core_conditions": native.get("core_conditions", []),
            "retained_plays": native.get("retained_plays", []),
            "advancements": native.get("advancements", []),
            "tags": native.get("tags", []),
            "identities": [{"name": item.name, "marked": item.marked} for item in actor.identities],
            "assets": native.get(
                "assets",
                [
                    {
                        "name": item.name,
                        "family": item.family,
                        "damaged": item.damaged,
                        "void": item.void,
                    }
                    for item in actor.assets
                    if not item.concealed
                ],
            ),
        }


def review_dossiers(game, viewer):
    campaign = game.store.campaign_id
    with game.store.engine.connect() as connection:
        connection.exec_driver_sql("BEGIN")
        game.authorize(connection, viewer, game=False)
        if not may_review(connection, game, viewer):
            raise WorkflowError("Campaign dossiers are restricted to the approved facilitator.")
        state = load_state(connection, campaign)
        records = [pilot_record(sheet, state) for sheet in state.sheets.values()]
        records.extend(cast_records(state, profiles(connection, campaign)))
    return {"dossiers": sorted(records, key=lambda row: (row["name"].casefold(), row["kind"]))}
