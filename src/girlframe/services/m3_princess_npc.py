"""Finite original-body NPC contact for native Princess sources."""

from typing import Any

from sqlalchemy import Connection

from girlframe.engine import m3_princess_sex as rules
from girlframe.engine.m2 import GameState
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
    _audit(game, c, contact.event, ("m3.princess_sex_consent",), contact.controller)
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
    game: GameService, c: Connection, state: GameState, value: rules.Session, own: Any, other: Any
) -> None:
    if value.bonded_source or value.changeling_source:
        raise WorkflowError("Keep NPC Princess independent of delegated or psychic sources")
    if value.learned_source is not None:
        from girlframe.services.m3_learned_sex import admit_source

        if not admit_source(
            game, c, state, value.actor, value.target, rules.RULE, value.learned_source
        ):
            raise WorkflowError("Recover the exact learned original NPC source")
    _npc_space(game, c, state, other)
    if own.inside_frame is not False or own.cell is None or own.cell != other.cell:
        raise WorkflowError("Preserve actual original bodies together for this invitation")
    if value.phase not in ("invited", "declined"):
        _prove_npc_contact(game, c, value)
        assert value.npc_contact is not None
        if other.cell != value.npc_contact.cell:
            raise WorkflowError("Renew actual NPC contact after movement")
