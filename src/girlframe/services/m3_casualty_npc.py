"""Finite original-body NPC contact for native Casualty sources."""

from typing import Any

from sqlalchemy import Connection

from girlframe.engine import m3_casualty as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_dose_up import _audit
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_oldgen_sex import _npc_space
from girlframe.services.onboarding import WorkflowError


def _prove_npc_contact(game: GameService, c: Connection, value: rules.SexSession) -> None:
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
    _audit(game, c, contact.event, ("m3.casualty_sex_confirmed",), contact.controller)
    born = _history(c, game, contact.event)
    saved = next(x for x in rules.records(born, rules.SexSession) if x.id == value.id)
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
    value: rules.SexSession,
    own: Any,
    other: Any,
) -> None:
    if value.learned_source or value.bonded_source or value.changeling_source:
        raise WorkflowError("NPC Casualty currently requires its genuine native source")
    _npc_space(game, c, state, other)
    if own.inside_frame is not False or own.cell is None or own.cell != other.cell:
        raise WorkflowError("Preserve actual original bodies together for this invitation")
    if value.phase not in ("invited", "declined"):
        _prove_npc_contact(game, c, value)
        assert value.npc_contact is not None
        if other.cell != value.npc_contact.cell:
            raise WorkflowError("Renew actual NPC contact after movement")
