"""Pure source-specific Heat/Identity ports; non-Girls never become proxy Pilot sheets."""

from pydantic import Field

from girlframe.engine.m2 import GameState, IdentityState, mark_identity, spend_heat
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve


class Commitment(Model):
    heat: int = Field(ge=0)
    identity: str | None = None
    gain: int = Field(default=0, ge=0, le=5)
    pair_share: int = Field(default=0, ge=0, le=5)


class Followup(Model):
    kind: str
    actor: ActorRef
    source_pdf: int


class Committed(Model):
    state: GameState
    followups: tuple[Followup, ...] = ()


def commit(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    prepared: Commitment,
    expected: str,
    *,
    require_current_profile: bool = True,
) -> Committed:
    state = GameState.model_validate_json(original.model_dump_json())
    view = resolve(state, actor, bindings, require_current_profile=require_current_profile)
    prepared = Commitment.model_validate_json(prepared.model_dump_json())
    if view.source_sha256 != expected:
        raise ValueError("STALE_RESOURCES: confirm the actual actor's current resources")
    followups: list[Followup] = []
    if view.rules == "girl_frame":
        sheet = state.sheets[actor.entity]
        was_full = all(x.marked for x in sheet.identities)
        if prepared.identity is not None:
            share = mark_identity(
                sheet, prepared.identity, prepared.gain, prepared.pair_share, state=state
            )
            if share:
                pair = next((x for x in bindings if x.owner == sheet.pair), None)
                if pair is None:
                    raise ValueError("The actual Pair's character binding is unavailable")
                resolve(
                    state,
                    ActorRef(kind="pilot", entity=str(pair.owner), incarnation=pair.character_id),
                    bindings,
                    require_current_profile=False,
                )
                state.sheets[str(pair.owner)].heat += share
                state.sheets[str(pair.owner)].revision += 1
        elif prepared.gain or prepared.pair_share:
            raise ValueError("Heat gain requires an actual eligible Identity")
        spend_heat(sheet, prepared.heat)
        sheet.revision += 1
        if (
            sheet.frame == "PROJECT ANKOU"
            and not was_full
            and all(x.marked for x in sheet.identities)
        ):
            followups.append(Followup(kind="ankou_feedback", actor=actor, source_pdf=84))
    elif view.rules == "handler_girl":
        context = next(x for x in state.director_contexts if x.id == actor.incarnation and x.active)
        if prepared.pair_share:
            raise ValueError("The actual Handler context has no Paired Identity or Pair")
        if prepared.identity is not None:
            identity: IdentityState | None = next(
                (x for x in context.identities if x.id == prepared.identity), None
            )
            if identity is None or identity.marked or not 1 <= prepared.gain <= 3:
                raise ValueError("Mark one actual unmarked ordinary Identity for one to three Heat")
            identity.marked = True
            state.handler_heat += prepared.gain
            context.revision += 1
        elif prepared.gain:
            raise ValueError("Heat gain requires an actual eligible Identity")
        if prepared.heat > state.handler_heat or (
            state.handler_heat >= 5 and prepared.heat != state.handler_heat
        ):
            raise ValueError("Spend available Heat; holding five or more requires spending all")
        state.handler_heat -= prepared.heat
    else:
        raise ValueError(
            "UNSUPPORTED_RULE: this role has no supported Girl Heat/Identity resource port"
        )
    return Committed(state=state, followups=tuple(followups))
