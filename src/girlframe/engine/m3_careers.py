"""End one original career and start a distinct incarnation without account inheritance."""

import json

from girlframe.engine.m2 import GameState, PilotSheet, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_career_state import (
    CareerArchive,
    CareerReturn,
    Ending,
    IncarnationBinding,
    UnlinkedCareer,
)


def binding(state: GameState, owner: int) -> IncarnationBinding | None:
    return next((x for x in reversed(state.incarnation_bindings) if x.owner == owner), None)


def profile_character(state: GameState, owner: int, profile: str, revision: int) -> str:
    """Stable SQL profile IDs retain old receipts; gameplay uses the current incarnation."""
    current = binding(state, owner)
    if current is None:
        if any(int(x.actor.entity) == owner for x in state.career_archives):
            raise ValueError("CAREER_ENDED: explicitly create the replacement character")
        return profile
    if (
        not current.active
        or current.profile_id != profile
        or revision < current.first_profile_revision
    ):
        raise ValueError("CAREER_ENDED: recover the original current incarnation")
    return current.character


def archive_for(state: GameState, actor: ActorRef) -> CareerArchive | None:
    return next((x for x in reversed(state.career_archives) if x.actor == actor), None)


def original_sheet(state: GameState, actor: ActorRef) -> PilotSheet:
    sheet = state.sheets.get(actor.entity)
    if sheet is not None and sheet.character_id == actor.incarnation:
        return sheet
    saved = archive_for(state, actor)
    if saved is None:
        raise ValueError("The original active or archived character is unavailable")
    return PilotSheet.model_validate_json(saved.sheet_json)


def tag_giver_is_current(state: GameState, tag: TagState) -> bool:
    if tag.giver_character is None:
        return True
    sheet = state.sheets.get(str(tag.giver))
    return sheet is not None and sheet.character_id == tag.giver_character


def tag_giver_ref(state: GameState, tag: TagState) -> ActorRef:
    """Recover the actual setter, including an ended original rather than its replacement."""
    from girlframe.engine.m3_actor_bonds import current_ref

    if tag.gm_setter_appointment is not None:
        raise ValueError("An OOC GM setter has no fictional actor or Bond authority")
    if tag.giver_actor is not None:
        return tag.giver_actor
    if tag.giver_character is not None:
        actor = ActorRef(kind="pilot", entity=str(tag.giver), incarnation=tag.giver_character)
        if any(x.actor == actor for x in state.career_archives) or tag_giver_is_current(state, tag):
            return actor
        raise ValueError("Recover the Tag's actual original setter")
    return current_ref(state, tag.giver)


def stamp_tag_givers(
    previous: GameState,
    original: GameState,
    source_event: str,
    *,
    gm_principal: tuple[int, str] | None = None,
    gm_grants: dict[str, tuple[int, str]] | None = None,
) -> GameState:
    """Bind only newly created Tags; existing historical setter evidence stays unchanged."""
    from girlframe.engine.m3_actor_bonds import current_ref

    if not source_event.strip():
        raise ValueError("New Tags require their actual creation source")
    state = GameState.model_validate_json(original.model_dump_json())
    before: dict[tuple[str, str | None, str], TagState] = {}
    for uid, sheet in previous.sheets.items():
        before.update({(uid, sheet.character_id, tag.id): tag for tag in sheet.tags})
    before.update({("handler", None, tag.id): tag for tag in previous.handler_tags})
    targets = [
        (uid, sheet.character_id, tag) for uid, sheet in state.sheets.items() for tag in sheet.tags
    ]
    targets.extend(("handler", None, tag) for tag in state.handler_tags)
    for uid, character, tag in targets:
        saved = before.get((uid, character, tag.id))
        if saved is not None:
            if (saved.gm_setter_appointment, saved.gm_setter_event, saved.gm_setter_grant) != (
                tag.gm_setter_appointment,
                tag.gm_setter_event,
                tag.gm_setter_grant,
            ):
                raise ValueError("An existing Tag cannot silently change its actual OOC setter")
            if saved.giver != tag.giver:
                raise ValueError("An existing Tag cannot silently change its numeric setter")
            if saved.giver_actor is not None and tag.giver_actor != saved.giver_actor:
                raise ValueError("An existing Tag cannot silently change its actual setter")
            continue
        if tag.gm_setter_appointment is not None:
            if (
                (
                    (gm_grants or {}).get(tag.gm_setter_grant)
                    if tag.gm_setter_grant is not None
                    else gm_principal
                )
                != (tag.giver, tag.gm_setter_appointment)
                or tag.giver_actor is not None
                or tag.giver_character is not None
                or tag.gm_setter_event not in (None, source_event)
            ):
                raise ValueError(
                    "New OOC Tags require the actual event actor's authenticated GM appointment"
                )
            tag.gm_setter_event = source_event
            continue
        if tag.gm_setter_event is not None:
            raise ValueError("An OOC setter event requires its real appointment principal")
        if tag.giver_actor is None:
            tag.giver_actor = current_ref(state, tag.giver)
        if tag.giver_actor.kind in ("pilot", "handler") and tag.giver_actor.entity != str(
            tag.giver
        ):
            raise ValueError("A new Tag cannot alias another human's original setter")
        if tag.giver_actor.kind == "pilot":
            if tag.giver_character not in (None, tag.giver_actor.incarnation):
                raise ValueError("The new Tag has conflicting original setter evidence")
            tag.giver_character = tag.giver_actor.incarnation
    return state


def can_pilot(state: GameState, actor: ActorRef) -> bool:
    return (
        actor.kind == "pilot"
        and actor.entity in state.sheets
        and state.sheets[actor.entity].character_id in (None, actor.incarnation)
        and not any(x.actor == actor for x in state.unlinked_careers)
    )


def unlink(original: GameState, actor: ActorRef, *, source_event: str, account: str) -> GameState:
    """Link reversal preserves the actual Girl, while removing her Frame capabilities."""
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != actor.incarnation
        or not can_pilot(state, actor)
        or not source_event.strip()
        or not account.strip()
        or len(account) > 1200
    ):
        raise ValueError("Reverse only the actual original Girl's existing Pilot link")
    snapshot = dict(
        frame=sheet.frame,
        frame_runtime=sheet.frame_runtime.model_dump(mode="json") if sheet.frame_runtime else None,
        assets=[x.model_dump(mode="json") for x in sheet.assets if x.family == "frame"],
    )
    state.unlinked_careers.append(
        UnlinkedCareer(
            actor=actor,
            source_event=source_event,
            account=account.strip(),
            frame_json=json.dumps(snapshot, sort_keys=True),
        )
    )
    sheet.assets = [x for x in sheet.assets if x.family != "frame"]
    sheet.frame_scrapped = True
    sheet.revision += 1
    # Surgery removes the ability to control; it grants no movement or rescue.
    state.placements = [
        x.model_copy(update={"mode": "inside_frame", "source_event": source_event})
        if x.actor == actor and x.mode == "piloting"
        else x
        for x in state.placements
    ]
    return state


def end(
    original: GameState,
    actor: ActorRef,
    *,
    reason: Ending,
    source_event: str,
    account: str,
    archive_id: str,
    profile_id: str,
    profile_revision: int,
) -> GameState:
    """A trusted source resolver calls this after its actual owned consequence selection."""
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.owner != int(actor.entity)
        or (sheet.character_id is not None and sheet.character_id != actor.incarnation)
        or not source_event.strip()
        or not archive_id.strip()
        or not account.strip()
        or len(account) > 1200
        or not profile_id
        or profile_revision < 1
    ):
        raise ValueError("End only the actual original active Girl through a recorded consequence")
    owner = int(actor.entity)
    if profile_character(state, owner, profile_id, profile_revision) != actor.incarnation:
        raise ValueError("STALE_CAREER: the profile belongs to another incarnation")
    if owner not in state.order or any(x.id == archive_id for x in state.career_archives):
        raise ValueError("The actual active Status slot and a new career archive are required")
    if reason in ("death", "execution"):
        from girlframe.engine.m3_doctor import prevent_death

        state, prevented = prevent_death(state, actor, source_event)
        if prevented:
            return state
    from girlframe.engine.m3_actor_bonds import migrate_actor, migrate_helpless
    from girlframe.engine.m3_enforcer import end_grasps
    from girlframe.engine.m3_physical import interrupt_journeys

    original_sheet_json = sheet.model_dump_json()
    state = interrupt_journeys(state, actor, source_event, account)
    state = end_grasps(state, actor, source_event)
    links: dict[str, object] = {
        "bonds": {k: v for k, v in state.bonds.items() if actor.entity in k.split(":")},
        "counterparts": {
            uid: other.character_id for uid, other in state.sheets.items() if uid != actor.entity
        },
        "placements": [x.model_dump(mode="json") for x in state.placements if x.actor == actor],
        "owned_obligations": [
            x.model_dump(mode="json") for x in state.obligations if x.owner == owner
        ],
        "incoming": [],
        "tag_observation": [],
        "npc_bonds": {
            npc.id: npc.bonds["pilot:" + actor.entity]
            for npc in state.world.npcs
            if "pilot:" + actor.entity in npc.bonds
        }
        if state.world
        else {},
    }
    # Preserve the old person as the edge endpoint before clearing numeric aliases.
    state = migrate_helpless(migrate_actor(state, actor, source_event), actor, source_event)
    incoming = []
    observation = []
    for uid, other in state.sheets.items():
        if uid == actor.entity:
            continue
        before = other.model_dump_json()
        related: dict[str, object] = {"character": other.character_id, "owner": uid}
        if other.mentor == owner:
            related["mentor"] = owner
            other.mentor = None
        if other.pair == owner:
            related["pair"] = owner
            other.pair = None
        if owner in other.helpless_against:
            related["helpless_against"] = owner
            other.helpless_against = tuple(x for x in other.helpless_against if x != owner)
        if other.frame_runtime:
            runtime = other.frame_runtime
            court = {k: v for k, v in runtime.court.items() if v != owner}
            strings = tuple(x for x in runtime.psych_strings if x != owner)
            if court != runtime.court or strings != runtime.psych_strings:
                related["frame_runtime"] = runtime.model_dump(mode="json")
                other.frame_runtime = runtime.model_copy(
                    update={"court": court, "psych_strings": strings}
                )
        for tag in other.tags:
            if owner in tag.observers:
                observation.append(dict(owner=uid, tag=tag.id, observers=list(tag.observers)))
                tag.observers = tuple(x for x in tag.observers if x != owner)
            if (
                tag.giver == owner
                and tag.giver_character is None
                and tag.gm_setter_appointment is None
            ):
                tag.giver_character = actor.incarnation
            if tag.giver == owner and tag.giver_actor is None and tag.gm_setter_appointment is None:
                tag.giver_actor = actor
        if len(related) > 2:
            incoming.append(related)
        if other.model_dump_json() != before:
            other.revision += 1
    links["incoming"], links["tag_observation"] = incoming, observation
    for tag in state.handler_tags:
        if tag.giver == owner and tag.giver_character is None and tag.gm_setter_appointment is None:
            tag.giver_character = actor.incarnation
        if tag.giver == owner and tag.giver_actor is None and tag.gm_setter_appointment is None:
            tag.giver_actor = actor
        tag.observers = tuple(x for x in tag.observers if x != owner)
    if state.world:
        npcs = []
        key = "pilot:" + actor.entity
        for npc in state.world.npcs:
            bonds = dict(npc.bonds)
            if key in bonds:
                bonds["archived_pilot:" + str(actor.incarnation)] = bonds.pop(key)
            npcs.append(npc.model_copy(update={"bonds": bonds}))
        links["rooms"] = [list(x) for x in state.world.rooms if owner in x]
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(npcs),
                "rooms": tuple(
                    tuple(uid for uid in room if uid != owner)
                    for room in state.world.rooms
                    if any(uid != owner for uid in room)
                ),
            }
        )
    state.bonds = {k: v for k, v in state.bonds.items() if actor.entity not in k.split(":")}
    # A source-locked Tag still needs its original setter's consent. Ending the setter's
    # career does not erase the restriction, and a replacement cannot grant that consent.
    state.obligations = [
        x for x in state.obligations if x.owner != owner or x.kind == "tag_rejection_permission"
    ]
    state.placements = [x for x in state.placements if x.actor != actor]
    state.scene_casts = [
        x.model_copy(
            update={
                "roles": tuple(role for role in x.roles if role.actor != actor),
                "revision": x.revision + 1,
            }
        )
        if any(role.actor == actor for role in x.roles)
        else x
        for x in state.scene_casts
    ]
    state.career_archives.append(
        CareerArchive(
            id=archive_id,
            actor=actor,
            ending=reason,
            source_event=source_event,
            account=account.strip(),
            profile_id=profile_id,
            profile_revision=profile_revision,
            position=state.order.index(owner),
            sheet_json=original_sheet_json,
            links_json=json.dumps(links, sort_keys=True),
        )
    )
    state.incarnation_bindings.append(
        IncarnationBinding(
            owner=owner,
            character=str(actor.incarnation),
            profile_id=profile_id,
            first_profile_revision=profile_revision,
            source_event=source_event,
            active=False,
        )
    )
    state.order = tuple(x for x in state.order if x != owner)
    del state.sheets[actor.entity]
    return GameState.model_validate_json(state.model_dump_json())


def replacement(
    original: GameState,
    archive_id: str,
    *,
    owner: int,
    new_character: str,
    profile_id: str,
    profile_revision: int,
    source_event: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    archive = next(
        (x for x in state.career_archives if x.id == archive_id and x.actor.entity == str(owner)),
        None,
    )
    current = binding(state, owner)
    if (
        archive is None
        or archive_for(state, archive.actor) != archive
        or current is None
        or current.active
        or current.character != archive.actor.incarnation
        or str(owner) in state.sheets
        or profile_id != archive.profile_id
        or profile_revision <= archive.profile_revision
        or not new_character.strip()
        or not source_event.strip()
        or any(x.character == new_character for x in state.incarnation_bindings)
        or any(x.actor.incarnation == new_character for x in state.career_archives)
        or any(x.character_id == new_character for x in state.sheets.values())
    ):
        raise ValueError("Explicitly start a new incarnation after the original career ended")
    state.incarnation_bindings.append(
        IncarnationBinding(
            owner=owner,
            character=new_character,
            profile_id=profile_id,
            first_profile_revision=profile_revision,
            source_event=source_event,
            active=True,
            previous_archive=archive_id,
        )
    )
    return state


def replacement_status(
    original: GameState,
    owner: int,
    character: str,
    position: int,
    source_event: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    current = binding(state, owner)
    if (
        current is None
        or not current.active
        or current.previous_archive is None
        or current.character != character
        or str(owner) in state.sheets
        or type(position) is not int
        or not 0 <= position <= len(state.order)
        or not source_event.strip()
    ):
        raise ValueError("The Handler chooses an actual starting Status for the new incarnation")
    state.incarnation_bindings.append(
        current.model_copy(
            update={
                "status_position": position,
                "status_event": source_event,
            }
        )
    )
    return state


def offer_return(
    original: GameState,
    archive_id: str,
    *,
    handler: int,
    identity: str,
    source_event: str,
    position: int,
    account: str,
    other_characters: tuple[ActorRef, ...],
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    archive = next((x for x in state.career_archives if x.id == archive_id), None)
    owner = int(archive.actor.entity) if archive else 0
    current = binding(state, owner)
    if (
        archive is None
        or archive_for(state, archive.actor) != archive
        or archive.ending not in ("imprisonment", "reserve")
        or state.handler != handler
        or current is None
        or not source_event.strip()
        or not account.strip()
        or len(account) > 1200
        or not identity.strip()
        or type(position) is not int
        or not 0 <= position <= len(other_characters)
        or tuple(int(x.entity) for x in other_characters)
        != tuple(x for x in state.order if x != owner)
        or any(x.id == identity for x in state.career_returns)
        or (
            archive.actor.entity in state.sheets
            and state.sheets[archive.actor.entity].character_id == archive.actor.incarnation
        )
    ):
        raise ValueError("The actual Handler may offer a source-archived Girl's return once")
    state.career_returns = [
        x.model_copy(update={"state": "withdrawn", "response_event": source_event})
        if x.archive == archive_id and x.state == "offered"
        else x
        for x in state.career_returns
    ]
    state.career_returns.append(
        CareerReturn(
            id=identity,
            archive=archive_id,
            owner=owner,
            handler=handler,
            handler_persona=state.handler_persona.id if state.handler_persona else None,
            source_event=source_event,
            current_character=current.character,
            other_characters=other_characters,
            position=position,
            account=account.strip(),
        )
    )
    return state


def return_original(
    original: GameState,
    identity: str,
    *,
    response_event: str,
    profile_id: str,
    profile_revision: int,
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    ticket = next((x for x in state.career_returns if x.id == identity), None)
    archive = next((x for x in state.career_archives if ticket and x.id == ticket.archive), None)
    current = binding(state, ticket.owner) if ticket else None
    if (
        ticket is None
        or ticket.state != "offered"
        or archive is None
        or archive_for(state, archive.actor) != archive
        or current is None
        or current.character != ticket.current_character
        or str(ticket.owner) in state.sheets
        or archive.profile_id != profile_id
        or profile_revision <= archive.profile_revision
        or ticket.handler != state.handler
        or ticket.handler_persona != (state.handler_persona.id if state.handler_persona else None)
        or tuple(int(x.entity) for x in ticket.other_characters) != state.order
        or not account.strip()
        or len(account) > 1200
        or not response_event.strip()
    ):
        raise ValueError("Reconfirm the actual Handler offer and original-owner return choice")
    for peer in ticket.other_characters:
        sheet = state.sheets.get(peer.entity)
        if sheet is None or (
            sheet.character_id is not None and sheet.character_id != peer.incarnation
        ):
            raise ValueError("The actual Status roster changed; request a fresh return offer")
    restored = PilotSheet.model_validate_json(archive.sheet_json)
    restored.character_id = archive.actor.incarnation
    restored.source_profile_revision = profile_revision
    restored.revision += 1
    frame = (
        restored.frame_runtime.id
        if restored.frame_runtime
        else "initial:" + str(restored.character_id)
    )
    if any(
        (x.frame_runtime.id if x.frame_runtime else "initial:" + str(x.character_id)) == frame
        for x in state.sheets.values()
    ):
        raise ValueError("The original Frame is assigned elsewhere; recover its actual disposition")
    state.sheets[str(ticket.owner)] = restored
    state.order = state.order[: ticket.position] + (ticket.owner,) + state.order[ticket.position :]
    links = json.loads(archive.links_json)
    counterparts = links.get("counterparts", {})
    # ActorRef edges already preserve this original's actual Bonds. Recreating UID
    # keys here would create a second authority or grant a replacement an old Bond.
    if restored.mentor is not None:
        peer_sheet = state.sheets.get(str(restored.mentor))
        if peer_sheet is None or peer_sheet.character_id != counterparts.get(str(restored.mentor)):
            restored.mentor = None
    if restored.pair is not None:
        peer_sheet = state.sheets.get(str(restored.pair))
        if peer_sheet is None or peer_sheet.character_id != counterparts.get(str(restored.pair)):
            restored.pair = None
    existing_debts = {x.id for x in state.obligations}
    from girlframe.engine.m2 import Obligation

    for saved in links.get("owned_obligations", []):
        if saved["id"] not in existing_debts:
            state.obligations.append(Obligation.model_validate_json(json.dumps(saved)))
    # The same actual vessel returns. No old map position, travel or piloting is invented.
    from girlframe.engine.m3_physical_state import Placement

    for saved in links.get("placements", []):
        placement = Placement.model_validate_json(json.dumps(saved))
        state.placements.append(
            placement.model_copy(
                update={
                    "girl_cell": None,
                    "frame_cell": None,
                    "mode": "inside_frame" if placement.mode == "piloting" else placement.mode,
                    "proposed_event": ticket.source_event,
                    "source_event": response_event,
                    "account": account.strip(),
                }
            )
        )
    state.incarnation_bindings.append(
        IncarnationBinding(
            owner=ticket.owner,
            character=str(archive.actor.incarnation),
            profile_id=profile_id,
            first_profile_revision=profile_revision,
            source_event=response_event,
            active=True,
            previous_archive=archive.id,
            status_position=ticket.position,
            status_event=ticket.source_event,
        )
    )
    state.career_returns = [
        x.model_copy(update={"state": "returned", "response_event": response_event})
        if x.id == identity
        else x
        for x in state.career_returns
    ]
    return GameState.model_validate_json(state.model_dump_json())
