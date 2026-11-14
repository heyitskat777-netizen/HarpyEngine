"""Finite original-body NPC contact for native and genuinely earned Stim sources."""

from typing import Any

from sqlalchemy import Connection

from girlframe.engine import m3_stim_sex as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_dose_up import _audit
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_oldgen_sex import _npc_space
from girlframe.services.onboarding import WorkflowError


def _prove_npc_contact(game: GameService, c: Connection, value: rules.Session) -> None:
    contact = value.npc_contact
    if contact is None or (
        contact.session,
        contact.target,
        contact.actor,
        contact.controller,
        contact.vessel,
        contact.actor_vessel,
        contact.cast,
        contact.event,
    ) != (
        value.id,
        value.target,
        value.actor,
        value.counterpart,
        value.target_vessel,
        value.actor_vessel,
        value.cast,
        value.consent_event,
    ):
        raise WorkflowError(
            "Recover the NPC controller's positive invitation-specific contact fact"
        )
    _audit(game, c, contact.event, ("m3.stim_sex_consent",), contact.controller)
    born = _history(c, game, contact.event)
    saved = rules.get(born, value.id)
    if (
        saved.npc_contact != contact
        or saved.phase != "accepted"
        or born.revision != contact.revision + 1
    ):
        raise WorkflowError("Preserve the actual canonical contact statement and revision")
    bindings = snapshot_profiles(c, game.store.campaign_id, born)
    own, other = resolve(born, value.actor, bindings), resolve(born, value.target, bindings)
    _npc_space(game, c, born, other)
    if (
        own.cell != contact.cell
        or other.cell != contact.cell
        or other.controller != contact.controller
        or own.inside_frame is not False
        or own.vessel_id != contact.actor_vessel
        or other.vessel_id != contact.vessel
    ):
        raise WorkflowError("Recover the actual original contact bodies and authored location")


def contact(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Session,
    own: Any,
    other: Any,
    *,
    pending_event: str | None = None,
) -> None:
    if value.bonded_source or value.changeling_source:
        raise WorkflowError("Keep NPC Stim independent of delegated or psychic sources")
    if value.learned_source is not None:
        from girlframe.services.m3_learned_sex import admit_source

        if not admit_source(
            game,
            c,
            state,
            value.actor,
            value.target,
            rules.RULE,
            value.learned_source,
            pending_event=pending_event,
        ):
            raise WorkflowError("Recover the exact earned lesson and original NPC source")
    _npc_space(game, c, state, other)
    if own.inside_frame is not False or own.cell is None or own.cell != other.cell:
        raise WorkflowError("Preserve actual original bodies together for this invitation")
    if value.phase not in ("invited", "declined"):
        _prove_npc_contact(game, c, value)
        assert value.npc_contact is not None
        if other.cell != value.npc_contact.cell:
            raise WorkflowError("Renew actual NPC contact after movement")


def active_drug(game: GameService, c: Connection, state: GameState, target: ActorRef) -> str | None:
    """Only an exact genuine unexpired original NPC drug can qualify a new Tag birth."""
    from girlframe.engine.m3_world_state import WorldTag
    from girlframe.services.m3_oldgen_sex import _counterpart
    from girlframe.services.m3_stim_sex import _drug

    for drug in rules.records(state, rules.Drug):
        if drug.target != target or not rules.active(state, drug):
            continue
        proved = _drug(game, c, state, drug.id)
        session = rules.get(state, proved.session)
        actual = _counterpart(game, c, state, target)
        if (
            target.kind != "npc"
            or not isinstance(proved.tag, WorldTag)
            or session.target != target
            or actual.controller != session.counterpart
            or actual.vessel_id != proved.vessel
        ):
            raise WorkflowError("Preserve original NPC drug, controller and body for Tag birth")
        return proved.id
    return None


def order_authority(
    game: GameService,
    c: Connection,
    state: GameState,
    issuer: ActorRef,
    target: ActorRef,
    *,
    effect_id: str | None = None,
    session_id: str | None = None,
) -> rules.Effect | None:
    """An actual reciprocal/low NPC choice supplies temporary relative authority only."""
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_stim_sex import _drug, prove_effect

    if issuer.kind != "npc" or target.kind != "pilot":
        return None
    # An opened source must not select an unrelated newer authority first.
    source_drugs = (
        {drug.id for drug in rules.records(state, rules.Drug) if drug.session == session_id}
        if session_id is not None
        else None
    )
    for effect in reversed(rules.records(state, rules.Effect)):
        if (
            effect.kind != "orders"
            or effect.giver != issuer
            or effect.target != target
            or effect_id is not None
            and effect.id != effect_id
            or source_drugs is not None
            and effect.drug not in source_drugs
        ):
            continue
        proved = prove_effect(game, c, state, effect.id)
        drug = _drug(game, c, state, proved.drug)
        if not rules.active(state, drug):
            continue
        source = rules.get(state, drug.session)
        bound = profiles(c, game.store.campaign_id)
        own, recipient = resolve(state, issuer, bound), resolve(state, target, bound)
        if (
            source.phase != "complete"
            or source.target != issuer
            or source.actor != target
            or own.controller != source.counterpart
            or own.vessel_id != source.target_vessel
            or recipient.controller != source.caster
            or recipient.vessel_id != drug.vessel
        ):
            raise WorkflowError("Preserve the exact original NPC, drugged Pilot and source bodies")
        return proved
    return None
