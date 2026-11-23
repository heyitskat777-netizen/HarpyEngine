"""A gated low Captured! consequence keeps the original person and parked Frame."""

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_bonds import rebind
from girlframe.engine.m3_actor_state import ActorRef, CastRole
from girlframe.engine.m3_captured import Capture
from girlframe.engine.m3_janus_storage import ids as stored_void
from girlframe.engine.m3_physical_state import ParkedFrame
from girlframe.engine.m3_void import FINAL
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import Access
from girlframe.services.m3_careers import end_in_transaction
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def available(game: GameService, c: Connection, viewer: GuildViewer) -> dict[str, ancillary.Book]:
    access = Access(game.store)
    for subsystem in ("world", "plays", "playbooks"):
        access.authorize(c, viewer, subsystem, director_response=True)
    registry = access.registry
    if registry is None:
        raise WorkflowError("Recover the exact approved Ancillary registry")
    try:
        registry.require_available(ancillary.RULE)
        registry.require_available(ancillary.CAPTURED_LOW)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    return {
        book: book
        for book, source in ancillary.STARTERS.items()
        if source.affiliation == "rebel"
        and registry.entry(source.rule).module in registry.enabled_modules
        and registry.entry(source.rule).verified
    }


def convert(
    c: Connection,
    game: GameService,
    state: GameState,
    case: Capture,
    book: ancillary.Book,
    identity: str,
    event: str,
    account: str,
) -> tuple[GameState, ActorRef]:
    sheet = state.sheets[case.girl.entity]
    body = next((p for p in state.placements if p.actor == case.girl), None)
    current = next((x for x in state.scene_casts if x.id == case.scene and x.open), None)
    if (
        body is None
        or body.custody != case.captor
        or body.girl_cell is None
        or sheet.frame_scrapped
        or body.occupied_frame_instance is not None
        or current is None
        or state.world is None
        or case.captor.kind != "npc"
        or case.current is None
        or case.current.roll.result != "low"
        or any(
            x.protected or x.paired or x.am_limiter or x.obsession_sources for x in sheet.identities
        )
        or any(x.actor == case.girl and x.stage not in FINAL for x in state.void_thresholds)
        or any(x.frame_instance == body.frame_instance for x in state.parked_frames)
        or any(x.asset_owner == case.girl or x.holder == case.girl for x in state.held_items)
        or sheet.sedation_locked
        or sheet.obsession_sources
        or stored_void(state, case.girl)
        or any(x.battery_asset is not None or x.concealed for x in sheet.assets)
    ):
        raise WorkflowError("The original captive requires a separate lifecycle or custody ruling")
    human = int(case.girl.entity)
    resulting = ActorRef(kind="external_pilot", entity="ancillary:" + case.id)
    existing_girl_assets = tuple(
        Asset(
            id=x.id,
            name=x.name,
            description=x.description,
            family="girl",
            damaged=x.damaged,
            void=x.void,
        )
        for x in sheet.assets
        if x.family == "girl"
    )
    origin = end_in_transaction(
        c,
        game,
        state,
        case.girl,
        reason="rebel_ancillary",
        source_event=event,
        account=account,
        archive_id=event,
    )
    assert origin.world is not None
    origin.parked_frames.append(
        ParkedFrame(
            owner=case.girl,
            frame_instance=body.frame_instance,
            cell=body.frame_cell,
            source_event=event,
            prior_event=body.source_event,
            core_id=sheet.frame_runtime.core_id if sheet.frame_runtime else None,
            frame_json=sheet.model_dump_json(),
        )
    )
    origin.world = update(
        origin.world,
        pilots=(
            *origin.world.pilots,
            AdversaryPilot(
                id=resulting.entity,
                name=sheet.callsign,
                cell=body.girl_cell,
                kind="rebel",
                girl=book,
                frame="Ancillary",
                assets=existing_girl_assets,
                faction=case.faction,
                controller=human,
            ),
        ),
    )
    ancillary.put(
        origin,
        ancillary.Character(
            actor=resulting,
            controller=human,
            event=event,
            draft=ancillary.CapturedDraft(
                name=sheet.callsign,
                book=book,
                original=case.girl,
                handler=case.captor,
                frame=body.frame_instance,
                capture=case.id,
            ),
            identities=(IdentityState(id=event + ":identity", name=identity, slot=0),),
            heat=sheet.heat,
            tags=tuple(sheet.tags),
        ),
    )
    origin = rebind(origin, case.girl, resulting, event)
    origin.scene_casts = [
        x.model_copy(
            update=dict(
                roles=(*x.roles, CastRole(actor=resulting, controller=human, source_event=event)),
                revision=x.revision + 1,
            )
        )
        if x.id == case.scene
        else x
        for x in origin.scene_casts
    ]
    return origin, resulting
