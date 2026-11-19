"""Actual original Harpy Identities and Core exposure for Visions of Infinity."""

from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_harpy_defeat import harpy, update
from girlframe.engine.m3_void_state import HarpyIdentity, HarpyState

KIND = "harpy_visions"


class Vision(Model):
    id: str
    scene: str
    channel: int
    harpy: ActorRef
    controller: int
    advancement: str
    subject: ActorRef
    account: str
    consent: str | None = None
    roll: Roll | None = None
    low_identities: tuple[HarpyIdentity, ...] = ()
    resolved: str | None = None


def records(state: GameState) -> tuple[Vision, ...]:
    return tuple(
        Vision.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, value: Vision) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


def can_replace(state: GameState, case: Vision) -> bool:
    sheet = state.sheets.get(case.subject.entity)
    if sheet is None or sheet.character_id != case.subject.incarnation:
        return False
    from girlframe.engine.m3_clone_am import additional_identities
    from girlframe.engine.m3_parasite_infection import controls_identity

    return (
        0 < len(case.low_identities) <= 4
        and not sheet.obsession_sources
        and sheet.frame != "PROJECT ANKOU"
        and not additional_identities(state, sheet.owner)
        and not any(
            x.protected
            or x.paired
            or x.am_limiter
            or x.obsession_sources
            or x.id in sheet.sedation_locked
            or controls_identity(state, case.subject, x.id)
            for x in sheet.identities
        )
        and not any(x.paired or x.obsession_sources for x in case.low_identities)
    )


def replace_low(state: GameState, case: Vision, event: str) -> GameState:
    if not can_replace(state, case) or harpy(state, case.harpy).identities != case.low_identities:
        raise ValueError("Recover the actual source Identities and unprotected original recipient")
    source = harpy(state, case.harpy)
    if isinstance(source, HarpyState):
        state = update(state, case.harpy, exposed=True)
    elif state.world is not None and any(
        x.id == case.harpy.entity and x.alive for x in state.world.pilots
    ):
        state.world = state.world.model_copy(
            update=dict(
                pilots=tuple(
                    x.model_copy(update=dict(exposed=True)) if x.id == case.harpy.entity else x
                    for x in state.world.pilots
                ),
            )
        )
    else:
        raise ValueError("Recover the original living Harpy Core")
    sheet = state.sheets[case.subject.entity]
    sheet.identities = [
        IdentityState(id=f"{event}:{slot}", name=original.name, slot=slot)
        for slot, original in enumerate(case.low_identities)
    ]
    sheet.revision += 1
    put(state, case.model_copy(update=dict(resolved=event)))
    return state
