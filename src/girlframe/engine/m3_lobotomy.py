"""Source-specific brain surgery effects; human descriptions are never generated."""

from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import GameState, IdentityState, PilotSheet
from girlframe.engine.m3_actor_bonds import current_ref, migrate_actor, set_depth
from girlframe.engine.m3_identity_slots import bind, replacement_slot
from girlframe.engine.m3_lobotomy_state import BlockedPlay, Plan, Response, Surgery

ROLLABLE = (
    "keep_your_head",
    "check_sensors",
    "engage",
    "disobey_orders",
    "flirt",
    "go_off_duty",
    "void_observation",
    "put_someone_beneath_you",
    "defeat",
    "dive_deep",
    "all_out_assault",
    "go_for_the_core",
)


def blocked_play(sheet: PilotSheet, play: str) -> BlockedPlay | None:
    return next((x for x in sheet.blocked_plays if x.play == play), None)


def name_removal_source(state: GameState, owner: int) -> Surgery | None:
    sheet = state.sheets.get(str(owner))
    if sheet is None or sheet.callsign != "":
        return None
    return next(
        (
            x
            for x in reversed(state.lobotomies)
            if x.phase == "applied"
            and x.applied_event
            and x.plan is not None
            and "name" in x.plan.options
            and x.plan.new_name.strip() == ""
            and x.subject.entity == str(owner)
            and x.subject.incarnation == sheet.character_id
        ),
        None,
    )


def _actual(state: GameState, surgery: Surgery) -> PilotSheet:
    if (
        current_ref(state, int(surgery.subject.entity)) != surgery.subject
        or current_ref(state, int(surgery.inflictor.entity)) != surgery.inflictor
        or state.handler != int(surgery.inflictor.entity)
    ):
        raise ValueError("Recover the actual original patient and surgery's inflictor")
    return state.sheets[surgery.subject.entity]


def _save(state: GameState, surgery: Surgery) -> GameState:
    state.lobotomies = [surgery if x.id == surgery.id else x for x in state.lobotomies]
    return GameState.model_validate_json(state.model_dump_json())


def prepare(
    original: GameState,
    identity: str,
    plan: Plan,
    source_event: str,
    *,
    allow_duplicate_labels: bool = False,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    surgery = next((x for x in state.lobotomies if x.id == identity), None)
    if surgery is None or surgery.phase != "plan" or not source_event:
        raise ValueError("Prepare the actual pending surgery once")
    _actual(state, surgery)
    if plan.forbidden_play is not None and plan.forbidden_play not in ROLLABLE:
        raise ValueError("Choose an actual known rolled Play, never a passive ability")
    if plan.other in (surgery.subject, surgery.inflictor):
        raise ValueError("Choose at most one distinct other character for the new Bond")
    # Validate all effects on a private copy before asking for actual descriptions.
    preview = surgery.model_copy(update={"plan": plan, "plan_event": source_event})
    _effects(state, preview, source_event, allow_duplicate_labels=allow_duplicate_labels)
    return _save(
        state,
        surgery.model_copy(update={"phase": "responses", "plan": plan, "plan_event": source_event}),
    )


def respond(
    original: GameState, identity: str, descriptions: dict[str, str], source_event: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    surgery = next((x for x in state.lobotomies if x.id == identity), None)
    if surgery is None or surgery.phase != "responses" or surgery.plan is None or not source_event:
        raise ValueError("Resume the actual patient's pending printed descriptions")
    _actual(state, surgery)
    if set(descriptions) != set(surgery.plan.options):
        raise ValueError("Describe exactly the selected surgery's printed responses")
    replies = tuple(
        Response(
            option=option,
            actor=surgery.subject,
            description=descriptions[option].strip(),
            source_event=source_event,
        )
        for option in surgery.plan.options
    )
    return _save(state, surgery.model_copy(update={"phase": "ready", "responses": replies}))


def _effects(
    original: GameState, surgery: Surgery, source_event: str, *, allow_duplicate_labels: bool
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = _actual(state, surgery)
    plan = surgery.plan
    if plan is None:
        raise ValueError("Recover the actual inflictor's surgery selections")
    if "memories" in plan.options:
        from girlframe.engine.m3_leviathan_obsession import require_unlocked

        require_unlocked(sheet.identities, (x.id for x in sheet.identities if not x.protected))
        sheet = bind(sheet)
        labels = CATALOG[sheet.girl]["identities"]
        protected = [x for x in sheet.identities if x.protected]
        occupied = {x.slot for x in protected if x.slot is not None}
        if set(plan.erase_slots) & occupied:
            raise ValueError("A printed protected starting Identity cannot be erased")
        locked_slots = {x.slot for x in sheet.identities if x.id in sheet.sedation_locked}
        sheet.identities = protected + [
            IdentityState(
                id=str(uuid5(NAMESPACE_URL, surgery.id + ":reset:" + str(index))),
                name=label,
                slot=index,
                marked=index in locked_slots,
            )
            for index, label in enumerate(labels)
            if index not in occupied and index not in plan.erase_slots
        ]
        sheet.sedation_locked = tuple(
            x.id for x in sheet.identities if x.slot in locked_slots and x.marked
        )
        state.sheets[surgery.subject.entity] = sheet
    if "play" in plan.options:
        assert plan.forbidden_play is not None
        if blocked_play(sheet, plan.forbidden_play) is not None:
            raise ValueError("Choose a Play the actual Girl can still roll")
        sheet.blocked_plays.append(
            BlockedPlay(play=plan.forbidden_play, surgery=surgery.id, source_event=source_event)
        )
    if "name" in plan.options:
        sheet.callsign = plan.new_name.strip()
    if "bonds" in plan.options:
        state = migrate_actor(state, surgery.subject, source_event)
        for edge in tuple(state.actor_bonds):
            if surgery.subject in (edge.first, edge.second):
                state = set_depth(state, edge.first, edge.second, 0, source_event)
        if plan.inflictor_depth:
            state = set_depth(
                state, surgery.subject, surgery.inflictor, plan.inflictor_depth, source_event
            )
        if plan.other is not None:
            state = set_depth(state, surgery.subject, plan.other, plan.other_depth, source_event)
        sheet = state.sheets[surgery.subject.entity]
    if "memory" in plan.options:
        from girlframe.engine.m3_leviathan_obsession import require_unlocked

        require_unlocked(
            sheet.identities, (plan.replace_identity,) if plan.replace_identity else ()
        )
        ordinary = [x for x in sheet.identities if not x.protected or x.paired or x.am_limiter]
        replaced = next(
            (x for x in sheet.identities if x.id == plan.replace_identity and not x.protected), None
        )
        if (len(ordinary) >= 4 and replaced is None) or (
            len(ordinary) < 4 and plan.replace_identity is not None
        ):
            raise ValueError("Replace an unprotected Identity only at the ordinary four-slot cap")
        if not allow_duplicate_labels and any(
            x.name.casefold() == plan.identity.strip().casefold()
            for x in sheet.identities
            if x is not replaced
        ):
            raise ValueError("Choose an implanted Identity distinct from the remaining labels")
        slot = replacement_slot(sheet, replaced.id if replaced else None)
        locked = bool(replaced and replaced.id in sheet.sedation_locked)
        if replaced:
            sheet.identities.remove(replaced)
            sheet.sedation_locked = tuple(x for x in sheet.sedation_locked if x != replaced.id)
        new = IdentityState(
            id=str(uuid5(NAMESPACE_URL, surgery.id + ":implant")),
            name=plan.identity.strip(),
            slot=slot,
            marked=locked,
        )
        sheet.identities.append(new)
        if locked:
            sheet.sedation_locked += (new.id,)
    sheet.revision += 1
    return state


def apply(
    original: GameState, identity: str, source_event: str, *, allow_duplicate_labels: bool
) -> GameState:
    surgery = next((x for x in original.lobotomies if x.id == identity), None)
    if surgery is None or surgery.phase != "ready" or not source_event:
        raise ValueError("The actual patient must supply every printed description first")
    state = _effects(original, surgery, source_event, allow_duplicate_labels=allow_duplicate_labels)
    return _save(
        state, surgery.model_copy(update={"phase": "applied", "applied_event": source_event})
    )
