"""Actual original-body Void thresholds and irreversible Apometanoia (PDF19,179)."""

from typing import Literal

from girlframe.engine import m3_actor_bonds as bonds
from girlframe.engine import m3_careers as careers
from girlframe.engine import m3_physical as physical
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_void_state import (
    HarpyAsset,
    HarpyIdentity,
    HarpyState,
    HarpyTag,
    VoidAnswer,
    VoidThreshold,
)
from girlframe.engine.m3_world_state import Gorgon

QUESTIONS = (
    "Are you prepared?",
    "Do you hear the voice of your Handler?",
    "Does anything still really matter to you other than this?",
    "Will you hesitate?",
    "Do you have any other choice?",
)
FINAL = frozenset({"prevented", "escaped", "converted", "dead", "overgrown_alive"})


def threshold(state: GameState, identity: str) -> VoidThreshold:
    value = next((x for x in state.void_thresholds if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original Void threshold")
    return value


def _save(state: GameState, value: VoidThreshold) -> GameState:
    state.void_thresholds = [value if x.id == value.id else x for x in state.void_thresholds]
    return state


def _copy(original: GameState, identity: str, event: str) -> tuple[GameState, VoidThreshold]:
    state = GameState.model_validate_json(original.model_dump_json())
    current = threshold(state, identity)
    if not event.strip() or current.stage in FINAL:
        raise ValueError("Use a new actual response to an unfinished original threshold")
    if any(x.get("kind") == "void_response" and x.get("event") == event for x in state.facts):
        raise ValueError("This original Void response has already been applied")
    state.facts.append(dict(kind="void_response", event=event, threshold=identity))
    return state, current


def start_threshold(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    family: Literal["girl", "frame"],
    event: str,
    source_work: str,
    *,
    source_action: str | None = None,
) -> tuple[GameState, VoidThreshold]:
    state = GameState.model_validate_json(original.model_dump_json())
    view = resolve(state, actor, bindings, require_current_profile=False)
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or view.frame_instance is None
        or not event.strip()
        or not source_work.strip()
    ):
        raise ValueError("A real Void threshold needs its original Girl and actual consequence")
    from girlframe.engine.m3_janus_storage import effective_assets, for_family

    actual_assets = effective_assets(state, actor)
    assets = [x for x in actual_assets if x.family == family]
    if not assets or not all(x.void for x in assets):
        raise ValueError("The actual family must have all of its Assets Void-altered")
    existing = next(
        (x for x in state.void_thresholds if x.actor == actor and x.stage not in FINAL), None
    )
    if existing is not None:
        if existing.frame_instance != view.frame_instance:
            raise ValueError("Recover the original affected Frame before adding another threshold")
        value = existing.model_copy(
            update={
                "source_works": tuple(dict.fromkeys((*existing.source_works, source_work))),
                "storage_points": tuple(
                    dict.fromkeys(
                        (
                            *existing.storage_points,
                            *(x.id for x in for_family(state, actor, family)),
                        )
                    )
                ),
            }
        )
        if family == "frame" and existing.family == "girl":
            value = value.model_copy(
                update={
                    "family": "frame",
                    "enclosed": view.inside_frame is True
                    and view.occupied_frame_instance == view.frame_instance,
                    "stage": (
                        "enclosed"
                        if view.inside_frame is True
                        and view.occupied_frame_instance == view.frame_instance
                        else "abandoned"
                    )
                    if existing.stage in ("allured", "questions") and not existing.answers
                    else existing.stage,
                }
            )
        return _save(state, value), value
    own = view.inside_frame is True and view.occupied_frame_instance == view.frame_instance
    mockingbird = has_rule(sheet, "girl.mockingbird.risk-factor", "MOCKINGBIRD")
    frame_assets = [x for x in actual_assets if x.family == "frame"]
    stage: Literal[
        "prevented",
        "resist_pending",
        "enclosed",
        "questions",
        "allured",
        "physical_review",
        "abandoned",
    ]
    if view.inside_frame is None:
        stage = "physical_review"
    elif family == "frame" and not own:
        stage = "abandoned"
    elif mockingbird and not (own and frame_assets and all(x.void for x in frame_assets)):
        stage = "prevented"
    elif mockingbird:
        stage = "resist_pending"
    elif own:
        stage = "enclosed" if family == "frame" else "questions"
    else:
        stage = "allured" if family == "girl" else "abandoned"
    value = VoidThreshold(
        id="void:" + source_work,
        actor=actor,
        frame_instance=view.frame_instance,
        family=family,
        source_event=event,
        source_action=source_action,
        source_works=(source_work,),
        storage_points=tuple(x.id for x in for_family(state, actor, family)),
        sheet_json=sheet.model_dump_json(),
        stage=stage,
        enclosed=family == "frame" and own,
        allure_persists=not mockingbird
        and bool([x for x in actual_assets if x.family == "girl"])
        and all(x.void for x in actual_assets if x.family == "girl"),
    )
    state.void_thresholds.append(value)
    return state, value


def begin_questions(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    identity: str,
    replace_identity: str,
    event: str,
    account: str,
) -> GameState:
    state, value = _copy(original, identity, event)
    if value.stage not in ("allured", "enclosed", "questions") or value.free_identity is not None:
        raise ValueError("Begin the original actual transformation only once")
    view = resolve(state, value.actor, bindings, require_current_profile=False)
    if not view.inside_frame:
        state = physical.cockpit_enter(
            state,
            bindings,
            value.actor,
            event,
            account,
            pilot=False,
            void_threshold=value.id,
        )
        view = resolve(state, value.actor, bindings, require_current_profile=False)
    if view.occupied_frame_instance != value.frame_instance:
        raise ValueError("Apometanoia requires entering her actual own affected Frame")
    sheet = state.sheets[value.actor.entity]
    chosen = next((x for x in sheet.identities if x.id == replace_identity), None)
    if chosen is None:
        raise ValueError("The original owner chooses one actual Identity to replace with Free")
    free = chosen.model_copy(update={"name": "Free"})
    sheet.identities = [free if x.id == chosen.id else x for x in sheet.identities]
    sheet.revision += 1
    return _save(
        state,
        value.model_copy(
            update=dict(stage="questions", free_identity=free.id, response_event=event)
        ),
    )


def confirm_approach(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    identity: str,
    replace_identity: str,
    event: str,
    account: str,
) -> GameState:
    """A separate actual Handler confirms the owner's completed stage-one arrival/embrace."""
    state, value = _copy(original, identity, event)
    view = resolve(state, value.actor, bindings, require_current_profile=False)
    body = next((x for x in state.placements if x.actor == value.actor), None)
    if (
        value.stage != "allured"
        or value.free_identity is not None
        or body is None
        or body.mode != "outside_frame"
        or body.custody is not None
        or body.incapacitated
        or not body.vitals_active
        or view.frame_scrapped
        or view.frame_instance != value.frame_instance
    ):
        raise ValueError(
            "Confirm only the original free capable Girl's actual arrival "
            "at her affected Vital Frame"
        )
    if physical.cockpit_lock(state, value.actor, value.frame_instance) is not None:
        raise ValueError("The actually closed Frame must first open its cockpit")
    chosen = next(
        (x for x in state.sheets[value.actor.entity].identities if x.id == replace_identity), None
    )
    if chosen is None:
        raise ValueError("The original owner must select the actual Identity she replaces")
    physical._source(state, event, account, value.actor)
    physical._save(
        state,
        body.model_copy(
            update=dict(
                mode="inside_frame", girl_cell=view.frame_cell, source_event=event, account=account
            )
        ),
    )
    state = physical._finish(state, value.actor, event, account, "apometanoia_actual_arrival")
    sheet = state.sheets[value.actor.entity]
    sheet.identities = [
        x.model_copy(update={"name": "Free"}) if x.id == replace_identity else x
        for x in sheet.identities
    ]
    sheet.revision += 1
    return _save(
        state,
        value.model_copy(
            update=dict(stage="questions", free_identity=replace_identity, response_event=event)
        ),
    )


def confirm_occupancy(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    identity: str,
    mode: Literal["outside_frame", "inside_frame", "piloting"],
    event: str,
    account: str,
    *,
    proposed_event: str | None = None,
) -> GameState:
    state, value = _copy(original, identity, event)
    if value.stage != "physical_review" or any(x.actor == value.actor for x in state.placements):
        raise ValueError("Confirm only this original body's genuinely unknown actual occupancy")
    actual = resolve(state, value.actor, bindings, require_current_profile=False)
    if mode == "piloting" and (
        actual.frame_scrapped or state.sheets[value.actor.entity].medical_state != "fit"
    ):
        raise ValueError(
            "Record occupancy without granting control to an unavailable Frame or injured Girl"
        )
    state, _ = physical.original_placement(
        state,
        bindings,
        value.actor,
        event,
        account,
        prior_event=proposed_event or value.source_event,
        mode=mode,
    )
    view = resolve(state, value.actor, bindings, require_current_profile=False)
    sheet = state.sheets[value.actor.entity]
    own = view.inside_frame is True and view.occupied_frame_instance == value.frame_instance
    mockingbird = has_rule(sheet, "girl.mockingbird.risk-factor", "MOCKINGBIRD")
    from girlframe.engine.m3_janus_storage import effective_assets

    frames = [x for x in effective_assets(state, value.actor) if x.family == "frame"]
    if value.family == "frame" and not own:
        stage = "abandoned"
    elif mockingbird:
        stage = "resist_pending" if own and frames and all(x.void for x in frames) else "prevented"
    elif own:
        stage = "enclosed" if value.family == "frame" else "questions"
    else:
        stage = "abandoned" if value.family == "frame" else "allured"
    return _save(
        state,
        value.model_copy(
            update=dict(stage=stage, enclosed=own and value.family == "frame", response_event=event)
        ),
    )


def answer_question(
    original: GameState,
    identity: str,
    owner: int,
    answer: bool,
    event: str,
    *,
    honest: Literal[True],
) -> GameState:
    state, value = _copy(original, identity, event)
    if (
        value.stage != "questions"
        or value.free_identity is None
        or owner != int(value.actor.entity)
    ):
        raise ValueError("Only the original Girl honestly answers her actual table question")
    answers = (
        *value.answers,
        VoidAnswer(
            number=len(value.answers), answer=answer, owner=owner, source_event=event, honest=honest
        ),
    )
    stage = "overgrown" if answer else "rebirth" if len(answers) == 5 else "questions"
    if answer:
        body = next((x for x in state.placements if x.actor == value.actor), None)
        if body is not None:
            state.placements = [
                x.model_copy(
                    update={"incapacitated": True, "vitals_active": False, "source_event": event}
                )
                if x.actor == value.actor
                else x
                for x in state.placements
            ]
        state.sheets[value.actor.entity].medical_state = "unconscious_injured"
    return _save(
        state,
        value.model_copy(
            update=dict(
                answers=answers,
                stage=stage,
                survival="pending" if answer else None,
                response_event=event,
            )
        ),
    )


def resolve_mockingbird(
    original: GameState,
    identity: str,
    event: str,
    *,
    child_action: str,
    in_control: bool,
    handler_enough: bool,
) -> GameState:
    """Trusted caller proves the actual linked completed Keep Your Head child, not any Play."""
    state, value = _copy(original, identity, event)
    if value.stage != "resist_pending" or not child_action:
        raise ValueError("Only the actual Mockingbird threshold's child can resist")
    stage = "prevented" if in_control and handler_enough else "enclosed"
    return _save(
        state,
        value.model_copy(
            update=dict(stage=stage, resistance_action=child_action, response_event=event)
        ),
    )


def _gorgon(state: GameState, value: VoidThreshold, supplied: Gorgon, event: str) -> ActorRef:
    if state.world is None or any(x.id == supplied.id for x in state.world.gorgons):
        raise ValueError("Choose a new actual Gorgon identity on the current world")
    sheet = state.sheets[value.actor.entity]
    frame_assets = [x for x in sheet.assets if x.family == "frame"]
    if {x.id for x in supplied.assets} != {x.id for x in frame_assets}:
        raise ValueError("The abandoned actual Frame keeps its original Asset identities")
    if any(
        asset.damaged != next(x.damaged for x in frame_assets if x.id == asset.id) or not asset.void
        for asset in supplied.assets
    ):
        raise ValueError("Actual Gorgon conversion preserves damage and does not erase Void")
    body = next((x for x in state.placements if x.actor == value.actor), None)
    cell = body.frame_cell if body is not None else None
    if supplied.cell != cell or supplied.position_event != event:
        raise ValueError(
            "The actual new Gorgon stays at the original known or unknown Frame position"
        )
    state.world = type(state.world).model_validate_json(
        state.world.model_copy(
            update={"gorgons": (*state.world.gorgons, supplied)}
        ).model_dump_json()
    )
    sheet.assets = [x for x in sheet.assets if x.family != "frame"]
    sheet.frame_scrapped = True
    sheet.revision += 1
    return ActorRef(kind="gorgon", entity=supplied.id)


def escape_frame(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    identity: str,
    damage_asset: str,
    gorgon: Gorgon,
    event: str,
    account: str,
) -> GameState:
    state, value = _copy(original, identity, event)
    if value.stage != "enclosed" or value.family != "frame":
        raise ValueError("Only the actual Frame enclosure grants this printed escape")
    sheet = state.sheets[value.actor.entity]
    asset = next(
        (x for x in sheet.assets if x.id == damage_asset and x.family == "girl" and not x.damaged),
        None,
    )
    if asset is None:
        raise ValueError("Escape actually damages one currently undamaged original Girl Asset")
    state = physical.escape_cockpit(
        state, bindings, value.actor, event, account, prior_event=value.source_event
    )
    next(x for x in state.sheets[value.actor.entity].assets if x.id == damage_asset).damaged = True
    ref = _gorgon(state, value, gorgon, event)
    return _save(
        state, value.model_copy(update=dict(stage="escaped", gorgon=ref, response_event=event))
    )


def abandoned_frame(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    identity: str,
    gorgon: Gorgon,
    event: str,
) -> GameState:
    """Delegated ruling: an already outside Girl pays no fictitious escape cost or movement."""
    state, value = _copy(original, identity, event)
    view = resolve(state, value.actor, bindings, require_current_profile=False)
    if (
        value.stage != "abandoned"
        or value.family != "frame"
        or view.inside_frame is None
        or (view.inside_frame and view.occupied_frame_instance == value.frame_instance)
    ):
        raise ValueError("Only an actually outside Girl has already avoided this Frame enclosure")
    ref = _gorgon(state, value, gorgon, event)
    return _save(
        state, value.model_copy(update=dict(stage="escaped", gorgon=ref, response_event=event))
    )


def prevent_entry(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    identity: str,
    protector: ActorRef,
    event: str,
    account: str,
) -> GameState:
    """Both owned agreements are proved by the caller; this applies an actual protective hold."""
    state, value = _copy(original, identity, event)
    if value.stage != "allured" or protector == value.actor:
        raise ValueError("Another actual person stops this Girl before she enters her own Frame")
    subject = resolve(state, value.actor, bindings, require_current_profile=False)
    guardian = resolve(state, protector, bindings, require_current_profile=False)
    if (subject.inside_frame and subject.occupied_frame_instance == value.frame_instance) or (
        subject.cell is not None and guardian.cell is not None and subject.cell != guardian.cell
    ):
        raise ValueError(
            "The actual guardian must stop her before own-Frame entry without invented travel"
        )
    if guardian.custody not in (None, "free") or not guardian.alive:
        raise ValueError("The actual guardian must be present and physically free")
    guardian_body = next((x for x in state.placements if x.actor == protector), None)
    if protector.kind == "pilot" and state.sheets[protector.entity].medical_state != "fit":
        raise ValueError("The actual guardian must be physically capable of this hold")
    if guardian_body and (
        guardian_body.incapacitated or not guardian_body.vitals_active or guardian_body.subsumed
    ):
        raise ValueError("The actual guardian must be physically capable of this hold")
    state, body = physical.original_placement(state, bindings, value.actor, event, account)
    if body.custody is not None:
        raise ValueError("Do not replace an existing actual captor with a protective hold")
    physical._source(state, event, account, value.actor)
    physical._save(state, body.model_copy(update={"custody": protector, "source_event": event}))
    state = physical._finish(state, value.actor, event, account, "void_protective_hold")
    return _save(
        state,
        value.model_copy(update=dict(stage="prevented", guardian=protector, response_event=event)),
    )


def overgrown_fate(
    original: GameState,
    identity: str,
    gorgon: Gorgon,
    event: str,
    account: str,
    *,
    alive: bool,
    archive_id: str,
    profile_id: str,
    profile_revision: int,
) -> GameState:
    """The actual Handler determines the uncertain factual survival; no automatic favorable fate."""
    state, value = _copy(original, identity, event)
    if value.stage != "overgrown" or value.survival != "pending" or type(alive) is not bool:
        raise ValueError("Determine the actual survival of the consumed original Girl")
    ref = _gorgon(state, value, gorgon, event)
    if alive:
        body = next((x for x in state.placements if x.actor == value.actor), None)
        if body is None:
            raise ValueError("Recover the actual original consumed body's vessel")
        state.placements = [
            x.model_copy(
                update=dict(
                    mode="inside_frame",
                    custody=ref,
                    occupied_frame_owner=None,
                    occupied_frame_instance=None,
                    incapacitated=True,
                    vitals_active=False,
                    source_event=event,
                )
            )
            if x.actor == value.actor
            else x
            for x in state.placements
        ]
        stage = "overgrown_alive"
    else:
        state = careers.end(
            state,
            value.actor,
            reason="death",
            source_event=event,
            account=account,
            archive_id=archive_id,
            profile_id=profile_id,
            profile_revision=profile_revision,
        )
        stage = "dead"
    return _save(
        state,
        value.model_copy(
            update=dict(
                stage=stage, survival="alive" if alive else "dead", gorgon=ref, response_event=event
            )
        ),
    )


def rebirth(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    identity: str,
    event: str,
    *,
    harpy_id: str,
    new_vessel: str,
    archive_id: str,
    profile_id: str,
    profile_revision: int,
    retained_identities: tuple[str, ...],
    new_identities: tuple[str, ...],
    retained_tags: tuple[str, ...],
    retained_plays: tuple[str, ...],
    owned_plays: tuple[str, ...],
    discarded_bonds: tuple[ActorRef, ...],
    assets: tuple[HarpyAsset, ...],
    account: str,
) -> GameState:
    state, value = _copy(original, identity, event)
    if value.stage != "rebirth" or any(x.id == harpy_id for x in state.harpy_states):
        raise ValueError("Only five actual honest no answers create this new Harpy body")
    if state.world and any(
        x.id == harpy_id
        for x in (
            *state.world.npcs,
            *state.world.pilots,
            *state.world.gorgons,
            *state.world.locations,
            *state.world.factions,
        )
    ):
        raise ValueError(
            "The actual new Harpy cannot replace another existing world's actor identity"
        )
    if any(x.vessel_id == new_vessel for x in state.placements) or any(
        new_vessel in (x.body_vessel, x.old_body_vessel) for x in state.harpy_states
    ):
        raise ValueError("The actual new Harpy body cannot reuse another original body's vessel")
    sheet = state.sheets[value.actor.entity]
    if (
        not set(retained_identities) <= {x.id for x in sheet.identities}
        or not set(retained_tags) <= {x.id for x in sheet.tags}
        or not set(retained_plays) <= set(owned_plays)
    ):
        raise ValueError("Retain only actual original owned resources")
    if {x.id for x in assets} != {x.id for x in sheet.assets} or any(
        x.family != next(a.family for a in sheet.assets if a.id == x.id)
        or not x.void
        or x.damaged != next(a.damaged for a in sheet.assets if a.id == x.id)
        or x.intrinsic != next(a.intrinsic for a in sheet.assets if a.id == x.id)
        or x.concealed != next(a.concealed for a in sheet.assets if a.id == x.id)
        for x in assets
    ):
        raise ValueError(
            "Rewrite the original Assets under their actual identities and Void families"
        )
    view = resolve(state, value.actor, bindings, require_current_profile=False)
    if not view.inside_frame or view.occupied_frame_instance != value.frame_instance:
        raise ValueError("The actual original Girl must still be in her transforming Frame")
    state, body = physical.original_placement(
        state,
        bindings,
        value.actor,
        event,
        account,
        prior_event=value.source_event,
        mode="inside_frame",
    )
    from girlframe.engine.m3_leviathan_obsession import require_unlocked

    require_unlocked(
        sheet.identities, (x.id for x in sheet.identities if x.id not in retained_identities)
    )
    identities = tuple(
        HarpyIdentity.model_validate(x.model_dump())
        for x in sheet.identities
        if x.id in retained_identities
    )
    identities += tuple(
        HarpyIdentity(id=f"{harpy_id}:new:{i}", name=name) for i, name in enumerate(new_identities)
    )
    # PDF179 replaces an Identity at birth; PDF181 grants Free in addition at completion.
    identities += (HarpyIdentity(id=harpy_id + ":free", name="Free"),)
    tags = tuple(
        HarpyTag(
            **{k: v for k, v in x.model_dump().items() if k != "giver_actor"},
            giver_ref=x.giver_actor,
        )
        for x in sheet.tags
        if x.id in retained_tags
    )
    state = bonds.migrate_actor(state, value.actor, event)
    for peer in discarded_bonds:
        if bonds.depth(state, value.actor, peer) == 0:
            raise ValueError("Discard only an actual original existing Bond")
        state = bonds.set_depth(state, value.actor, peer, 0, event)
    archived = careers.end(
        state,
        value.actor,
        reason="harpy",
        source_event=event,
        account=account,
        archive_id=archive_id,
        profile_id=profile_id,
        profile_revision=profile_revision,
    )
    harpy = HarpyState(
        id=harpy_id,
        origin=value.actor,
        controller=sheet.owner,
        name=sheet.callsign,
        source_event=event,
        original_archive=archive_id,
        old_body_vessel=body.vessel_id,
        body_vessel=new_vessel,
        frame_instance=value.frame_instance,
        original_girl=sheet.girl,
        original_frame=sheet.frame,
        cell=view.cell,
        frame_cell=view.frame_cell,
        heat=sheet.heat,
        permissions=sheet.permissions,
        assets=assets,
        identities=identities,
        tags=tags,
        plays=retained_plays,
        blocked_plays=tuple(sheet.blocked_plays),
    )
    archived.harpy_states.append(harpy)
    ref = ActorRef(kind="external_pilot", entity=harpy_id)
    archived = bonds.rebind(archived, value.actor, ref, event)
    count = 1
    if archived.strain:
        from girlframe.engine.m3_strain import effective_levels

        if effective_levels(archived.strain)["void"] == "high" or any(
            x.track == "void" and x.severity == "high" for x in archived.strain.events
        ):
            count = 2
        if any(x.track == "void" for x in archived.strain.endgames):
            count = 3
    converted = _save(
        archived,
        value.model_copy(
            update=dict(
                stage="converted",
                resulting_actor=ref,
                response_event=event,
                pending_advancements=count,
            )
        ),
    )
    from girlframe.engine.m3_tag_permissions import record_conversion

    return record_conversion(converted, value.actor, ref, archive_id, retained_tags, event)
