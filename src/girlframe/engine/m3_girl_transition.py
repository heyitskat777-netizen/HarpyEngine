"""Girl book change reconciles rule-specific setup without a free character reset."""

from girlframe.engine.creation_details import BODY_PARTS, DesireChoice
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, has_rule
from girlframe.engine.m3_girl_transition_state import BodyPart, GirlSetup, Plan
from girlframe.engine.m3_standards import ready as standards_ready


def starting_investors(state: GameState, owner: ActorRef) -> set[str]:
    if state.world is None:
        return set()
    return {
        x.npc
        for x in state.world.starting_npc_links
        if x.owner == int(owner.entity) and x.character_id == owner.incarnation
    }


def validate(
    state: GameState, owner: ActorRef, epoch: str, plan: Plan, bindings: tuple[ProfileBinding, ...]
) -> None:
    actor = resolve(state, owner, bindings, require_current_profile=False)
    sheet = state.sheets[owner.entity]
    if (
        actor.rules != "girl_frame"
        or not sheet.girl_runtime
        or sheet.girl_runtime.baseline_event != epoch
    ):
        raise ValueError("Recover this original Girl and the actual current baseline epoch")
    book = sheet.girl
    if book == "OLDGEN":
        if len(plan.maxims) != 2:
            raise ValueError("Choose exactly two printed maxims")
    elif plan.maxims:
        raise ValueError("Maxim setup belongs to Oldgen")
    if book == "VATGROWN":
        expected = starting_investors(state, owner)
        if (
            not plan.dna_basis.strip()
            or not expected
            or {x.npc for x in plan.investors} != expected
        ):
            raise ValueError(
                "Name the DNA basis and choose desires for each actual starting NPC investor"
            )
    elif plan.dna_basis or plan.investors:
        raise ValueError("Investor setup belongs to Vatgrown")
    if book == "BONDED":
        if plan.pair is None or plan.paired_identity is None:
            raise ValueError("Choose your actual Pair and one ordinary Identity to make Paired")
        other = resolve(state, plan.pair, bindings, require_current_profile=False)
        if other.rules != "girl_frame" or plan.pair == owner:
            raise ValueError("Your Pair is another actual Girl")
        target = next((x for x in sheet.identities if x.id == plan.paired_identity), None)
        if target is None or (target.protected and not target.paired):
            raise ValueError("Only the owner may select an ordinary/own Paired Identity")
        existing = {x.id for x in sheet.identities if x.paired}
        if existing and target.id not in existing:
            raise ValueError("Retain the already protected Paired Identity; do not add another")
        peer = state.sheets[plan.pair.entity]
        if has_rule(peer, "girl.bonded.bonded-pair", "BONDED") and peer.pair not in (
            None,
            int(owner.entity),
        ):
            raise ValueError("Resolve the other Bonded Girl's conflicting existing Pair first")
    elif plan.pair is not None or plan.paired_identity is not None:
        raise ValueError("Pair setup belongs to Bonded")


def apply(
    original: GameState,
    owner: ActorRef,
    epoch: str,
    plan: Plan,
    bindings: tuple[ProfileBinding, ...],
    event: str,
    *,
    mentor: ActorRef | None = None,
    callsign: str | None = None,
    handler: ActorRef | None = None,
    appointment: str | None = None,
    handler_desires: DesireChoice | None = None,
) -> GameState:
    validate(original, owner, epoch, plan, bindings)
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets[owner.entity]
    runtime = sheet.girl_runtime or GirlRuntime()
    previous = runtime.setup
    if sheet.girl == "PRINCESS" and not standards_ready(sheet):
        raise ValueError(
            "All three actual standards must be supplied before completing the new baseline"
        )
    if sheet.girl == "NEWGIRL":
        if (
            mentor is None
            or mentor == owner
            or not callsign
            or not callsign.strip()
            or len(callsign) > 80
        ):
            raise ValueError("The assigned actual Mentor must supply the callsign")
        if resolve(state, mentor, bindings, require_current_profile=False).rules != "girl_frame":
            raise ValueError("The assigned Mentor must be another actual Girl")
        if state.sheets[mentor.entity].mentor == int(owner.entity) and has_rule(
            state.sheets[mentor.entity], "girl.newgirl.mentor", "NEWGIRL"
        ):
            raise ValueError("Reciprocal Mentor authority cannot be installed")
        sheet.mentor = int(mentor.entity)
        sheet.callsign = callsign.strip()
        state = set_depth(state, owner, mentor, 2 if depth(state, owner, mentor) == 2 else 1, event)
        sheet = state.sheets[owner.entity]
    if sheet.girl == "BONDED":
        assert plan.pair is not None
        target = next(x for x in sheet.identities if x.id == plan.paired_identity)
        target.name = "Hers"
        target.paired = True
        target.protected = True
        sheet.pair = int(plan.pair.entity)
        state = set_depth(state, owner, plan.pair, 2, event)
        sheet = state.sheets[owner.entity]
    if sheet.girl == "VATGROWN" and (
        handler_desires is None or handler is None or appointment is None
    ):
        raise ValueError("The actual current Handler must provide their own investor desires")
    parts = previous.body_parts if previous else ()
    if sheet.girl == "CASUALTY" and not parts:
        parts = tuple(BodyPart(name=x) for x in BODY_PARTS)
    setup = GirlSetup(
        epoch=epoch,
        book=sheet.girl,
        source_event=event,
        account=plan.account,
        mentor=mentor if sheet.girl == "NEWGIRL" else previous.mentor if previous else None,
        pair=plan.pair if sheet.girl == "BONDED" else previous.pair if previous else None,
        paired_identity=plan.paired_identity
        if sheet.girl == "BONDED"
        else previous.paired_identity
        if previous
        else None,
        maxims=plan.maxims if sheet.girl == "OLDGEN" else previous.maxims if previous else (),
        dna_basis=plan.dna_basis
        if sheet.girl == "VATGROWN"
        else previous.dna_basis
        if previous
        else "",
        investors=plan.investors
        if sheet.girl == "VATGROWN"
        else previous.investors
        if previous
        else (),
        handler_desires=handler_desires
        if sheet.girl == "VATGROWN"
        else previous.handler_desires
        if previous
        else None,
        handler=handler,
        appointment=appointment,
        body_parts=parts,
    )
    sheet.girl_runtime = runtime.model_copy(update={"setup": setup})
    sheet.revision += 1
    return state
