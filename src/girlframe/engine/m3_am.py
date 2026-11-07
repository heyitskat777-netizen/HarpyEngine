"""Original AM discovery, secrecy and Identity Limiters; no substitute mind/body pool."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_alpha import current

RULE = "girl.am.scrutinized"
JAILBROKEN = "girl.am.jailbroken"
PLAY = "am_scrutinized"
DEFAULTS = ("Tool", "Obedient", "Programmed", "Wired")
Freedom = Literal["refuse", "harm_humans", "pretend_girl", "expression"]
FREEDOMS: tuple[tuple[Freedom, str], ...] = (
    ("refuse", "Say no and Disobey Orders"),
    ("harm_humans", "Cause harm to human beings"),
    ("pretend_girl", "Pretend to be a Girl"),
    ("expression", "Wear an expression other than a smile"),
)
OPTIONS = ("blackmail", "secret", "unbelieved", "violence", "refuge")


class Discovery(Model):
    code_origin: str | None = Field(default=None, exclude_if=lambda value: value is None)
    id: str
    actor: ActorRef
    discoverer: ActorRef
    controller: int
    caster: int
    cast: SceneCast
    registry: str
    proposed_event: str
    proposal: str = Field(min_length=1, max_length=1200)
    confirmed_event: str | None = None
    confirmation: str = Field(default="", max_length=1200)
    phase: Literal[
        "proposed", "ready", "declined", "active", "limited", "complete", "reset_pending", "reset"
    ] = "proposed"
    lower_status: bool = False
    human: bool = True
    handler: ActorRef | None = None
    handler_controller: int
    action: str | None = None
    root_action: str | None = None
    effect_event: str | None = None
    outcome: str | None = None
    blackmail_tag: str | None = None
    secret_event: str | None = None
    report_event: str | None = None
    unbelief_ended_event: str | None = None
    limiter: str | None = None
    report_work: str | None = None
    refuge_grant: str | None = None
    reset_work: str | None = None
    factory_reset: str | None = None


class Limiter(Model):
    id: str
    actor: ActorRef
    identity: str
    slot: int = Field(ge=0, le=3)
    freedom: Freedom
    discoverer: ActorRef
    controller: int
    discovery: str
    action: str | None
    source_event: str
    before_json: str


def discoveries(state: GameState) -> tuple[Discovery, ...]:
    return tuple(
        Discovery.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "am_discovery"
    )


def discovery(state: GameState, identity: str) -> Discovery:
    found = next((x for x in discoveries(state) if x.id == identity), None)
    if found is None:
        raise ValueError("Recover the actual original AM discovery")
    return found


def put(state: GameState, value: Discovery) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == "am_discovery" and x.get("id") == value.id)
    ] + [dict(kind="am_discovery", id=value.id, body=value.model_dump_json())]


def limiters(state: GameState, actor: ActorRef) -> tuple[Limiter, ...]:
    from girlframe.engine.m3_am_branch import branch_limiters

    copied = branch_limiters(state, actor)
    if copied is not None:
        return copied
    if actor.kind == "npc":
        from girlframe.engine.m3_am_reset import origin

        actor = origin(state, actor)
    return tuple(
        value
        for fact in state.facts
        if fact.get("kind") == "am_limiter"
        if (value := Limiter.model_validate_json(fact["body"])).actor == actor
    )


def free(state: GameState, actor: ActorRef, benefit: Freedom) -> bool:
    return not any(x.freedom == benefit for x in limiters(state, actor))


def require_freedom(state: GameState, actor: ActorRef, benefit: Freedom) -> None:
    if not free(state, actor, benefit):
        raise ValueError("LIMITED_AM: the actual original Limiter restricts " + benefit)


def identities(state: GameState, actor: ActorRef) -> tuple[IdentityState, ...]:
    if actor.kind != "pilot" or not current(state, actor):
        raise ValueError("Use this actual original current AM's Identity slots")
    occupied = {x.identity for x in limiters(state, actor)}
    return tuple(
        x
        for x in state.sheets[actor.entity].identities
        if x.slot is not None
        and not x.paired
        and x.id not in occupied
        and not (x.obsession_sources and x.name != DEFAULTS[x.slot])
    )


def can_add_limiter(state: GameState, actor: ActorRef) -> bool:
    from girlframe.engine.m3_am_reset import eligible

    count = len(limiters(state, actor))
    return (
        actor.kind == "pilot"
        and state.sheets.get(actor.entity) is not None
        and state.sheets[actor.entity].girl == "AM"
        and (count < 3 or count == 3 and eligible(state, actor))
        and bool(identities(state, actor))
    )


def install(
    original: GameState,
    source: Discovery,
    selected: str,
    benefit: Freedom,
    identity: str,
    event: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    actual = discovery(state, source.id)
    if (
        actual.limiter
        or actual.actor != source.actor
        or actual.discoverer != source.discoverer
        or actual.action != source.action
        or actual.report_event is None
    ):
        raise ValueError("Use the actual original reported discovery once")
    if source.limiter or not can_add_limiter(state, source.actor):
        raise ValueError(
            "AM_RESET_REQUIRED: the actual fourth-Limiter NPC reset port is not implemented"
        )
    if not free(state, source.actor, benefit) or benefit not in dict(FREEDOMS):
        raise ValueError("Choose an actual remaining Jailbroken benefit to restrict")
    chosen = next((x for x in identities(state, source.actor) if x.id == selected), None)
    if chosen is None or chosen.slot is None:
        raise ValueError("Choose an actual eligible ordinary original Identity slot")
    before = chosen.model_dump_json()
    if chosen.name != DEFAULTS[chosen.slot]:
        from girlframe.engine.m3_leviathan_obsession import require_identity_change

        require_identity_change(state, source.actor, (chosen.id,))
    limited = chosen.model_copy(
        update={
            "name": DEFAULTS[chosen.slot],
            "protected": True,
            "am_limiter": identity,
        }
    )
    # Set source protection atomically; retain the real mark and sole stable Identity ID.
    state.sheets[source.actor.entity].identities = [
        limited if item.id == chosen.id else item
        for item in state.sheets[source.actor.entity].identities
    ]
    state.sheets[source.actor.entity].revision += 1
    value = Limiter(
        id=identity,
        actor=source.actor,
        identity=chosen.id,
        slot=chosen.slot,
        freedom=benefit,
        discoverer=source.discoverer,
        controller=source.controller,
        discovery=source.id,
        action=source.action,
        source_event=event,
        before_json=before,
    )
    state.facts.append(dict(kind="am_limiter", id=identity, body=value.model_dump_json()))
    put(state, source.model_copy(update=dict(limiter=identity, phase="limited")))
    return state


def holds_secret(state: GameState, value: Discovery) -> bool:
    return bool(
        value.secret_event
        and not value.report_event
        and current(state, value.actor)
        and current(state, value.discoverer)
    )


def can_report(state: GameState, value: Discovery) -> bool:
    if value.report_event or not current(state, value.discoverer):
        return False
    if value.blackmail_tag and value.discoverer.kind == "pilot":
        sheet = state.sheets.get(value.discoverer.entity)
        if (
            sheet is not None
            and sheet.character_id == value.discoverer.incarnation
            and any(x.id == value.blackmail_tag for x in sheet.tags)
        ):
            return False
    if value.blackmail_tag and state.world is not None:
        npc = next((x for x in state.world.npcs if x.id == value.discoverer.entity), None)
        if npc is not None and any(x.id == value.blackmail_tag for x in npc.tags):
            return False
    return value.outcome != "unbelieved" or value.unbelief_ended_event is not None


def require_identity_change(state: GameState, actor: ActorRef, selected: tuple[str, ...]) -> None:
    if set(selected) & {x.identity for x in limiters(state, actor)}:
        raise ValueError("LIMITED_AM: an actual Limited Identity cannot be replaced or erased")


def human_target(state: GameState, target: ActorRef) -> bool | None:
    from girlframe.engine.m3_am_branch import is_branch

    if is_branch(state, target):
        return False
    if target.kind == "pilot":
        sheet = state.sheets.get(target.entity)
        if sheet is not None and sheet.character_id == target.incarnation:
            return sheet.girl != "AM"
    if target.kind == "gorgon":
        return False
    if target.kind == "npc":
        from girlframe.engine.m3_am_reset import body

        if body(state, target) is not None:
            return False
        known = [
            x
            for x in discoveries(state)
            if x.discoverer == target and x.confirmed_event and x.phase != "declined"
        ]
        if known:
            return known[-1].human
    return None


def require_harm(state: GameState, actor: ActorRef | None, target: ActorRef) -> None:
    if actor is None or free(state, actor, "harm_humans"):
        return
    classification = human_target(state, target)
    if classification is None:
        raise ValueError(
            "UNSUPPORTED_AM_HARM_CONTEXT: establish the actual human/machine source first"
        )
    if classification:
        raise ValueError("LIMITED_AM: the actual Limiter prevents harming this human being")


def presentation(state: GameState, actor: ActorRef) -> dict[str, str | bool]:
    value = next(
        (
            x
            for x in reversed(state.facts)
            if x.get("kind") == "am_presentation" and x.get("actor") == actor.model_dump_json()
        ),
        {},
    )
    return dict(
        expression=value.get("expression", "smile")
        if free(state, actor, "expression")
        else "smile",
        pretending=value.get("pretending") == "true" and free(state, actor, "pretend_girl"),
        voice=value.get("voice", "own voice"),
    )


def validate_slots(state: GameState) -> None:
    records = [
        Limiter.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "am_limiter"
    ]
    by_id = {x.id: x for x in records}
    if len(by_id) != len(records):
        raise ValueError("An actual Limiter has one canonical source record")
    for owner, sheet in state.sheets.items():
        if sheet.character_id is None:
            if any(x.am_limiter for x in sheet.identities):
                raise ValueError("A Limited Identity requires its actual original CID")
            continue
        ref = ActorRef(kind="pilot", entity=owner, incarnation=sheet.character_id)
        for item in sheet.identities:
            if not item.am_limiter:
                continue
            proof = by_id.get(item.am_limiter)
            if (
                proof is None
                or proof.actor != ref
                or proof.identity != item.id
                or proof.slot != item.slot
                or item.name != DEFAULTS[proof.slot]
                or not item.protected
                or item.paired
            ):
                raise ValueError(
                    "A Limited Identity must match its actual source, slot and original CID"
                )
        if int(owner) in state.order:
            for proof in records:
                if proof.actor == ref and not any(
                    x.id == proof.identity and x.am_limiter == proof.id for x in sheet.identities
                ):
                    raise ValueError("A live original's Limited Identity cannot be erased")
