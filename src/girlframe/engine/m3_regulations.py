"""Standing regulations require actual human facts, never passive chat inference."""

from girlframe.engine.m2 import GameState, Obligation
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_regulation_state import Breach, Regulation


def actor_ref(state: GameState, owner: int, bindings: dict[int, str] | None = None) -> ActorRef:
    if owner == state.handler:
        if any(x.active for x in state.director_contexts):
            raise ValueError("The Handler currently uses Girl rules in the Director's presence")
        return ActorRef(kind="handler", entity=str(owner))
    sheet = state.sheets.get(str(owner))
    identity = sheet.character_id if sheet else None
    supplied = (bindings or {}).get(owner)
    if identity is not None and supplied is not None and identity != supplied:
        raise ValueError("The supplied character binding disagrees with its actual sheet")
    identity = identity or supplied
    if sheet is None or owner not in state.order or identity is None:
        raise ValueError("Recover the original character binding before this regulation")
    return ActorRef(kind="pilot", entity=str(owner), incarnation=identity)


def impose(
    state: GameState,
    subject: int,
    inflictor: int,
    text: str,
    disclosed: bool,
    identity: str,
    source: str,
    bindings: dict[int, str] | None = None,
) -> Regulation:
    if not text.strip() or len(text) > 1200 or not source or state.handler is None:
        raise ValueError("State the behavioural rule and its actual imposition source")
    if any(x.id == identity for x in state.regulations):
        raise ValueError("This regulation already exists")
    return Regulation(
        id=identity,
        subject=actor_ref(state, subject, bindings),
        inflictor=actor_ref(state, inflictor, bindings),
        knowing_handler=actor_ref(state, state.handler),
        rule=text.strip(),
        disclosed=disclosed,
        source_event=source,
    )


def breach(
    original: GameState,
    identity: str,
    handler: int,
    evidence: str,
    source: str,
    obligation: str,
    bindings: dict[int, str] | None = None,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    rule = next((x for x in state.regulations if x.id == identity), None)
    actual_handler = actor_ref(state, handler)
    if rule is None or handler != state.handler or actual_handler != rule.knowing_handler:
        raise ValueError("Only the actual informed Handler may record this rule's breach")
    subject = int(rule.subject.entity)
    if actor_ref(state, subject, bindings) != rule.subject:
        raise ValueError("STALE_CHARACTER: this rule belongs to an earlier character")
    if not evidence.strip() or len(evidence) > 1200 or not source or not obligation:
        raise ValueError("Record the actual observed breach, without inventing a player response")
    if any(x.id == obligation for x in state.obligations) or any(
        x.source_event == source for x in rule.breaches
    ):
        raise ValueError("This actual breach already has its discipline cause")
    updated = rule.model_copy(
        update={
            "breaches": (
                *rule.breaches,
                Breach(
                    source_event=source,
                    evidence=evidence.strip(),
                    handler=actual_handler,
                    obligation=obligation,
                ),
            )
        }
    )
    state.regulations = [updated if x.id == identity else x for x in state.regulations]
    state.obligations.append(
        Obligation(
            id=obligation,
            kind="punishment",
            owner=subject,
            target=handler,
            action=source,
            details={
                "source_pdf": "17",
                "regulation": identity,
                "cause": "strict_regulations",
                "character_id": rule.subject.incarnation or "",
            },
        )
    )
    return state
