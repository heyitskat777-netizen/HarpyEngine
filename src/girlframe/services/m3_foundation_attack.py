"""An independent Pilot's actual attack can resolve the original site's fate."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_foundation_attack as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_collateral import stage_loss
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_rebel_frame_theft import base as require_base
from girlframe.engine.m3_strain_state import Trigger
from girlframe.engine.m3_world import destroy
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_engage import completed_interception
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_rebel_ambush import _cast
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    source: str,
    base: str,
    pilot: str,
) -> None:
    site = require_base(state, base)
    actor = rules.pilot(state, pilot)
    handler = active_handler(state)
    if (
        handler is None
        or not HandlerService(strain.store)._member(c, actor.controller)
        or any(x.id == row["id"] for x in rules.attacks(state))
    ):
        raise WorkflowError("Recover the original Foundation Pilot and preparing period")
    rules.save(
        state,
        rules.Attack(
            id=row["id"],
            source=source,
            period=row["off_duty_id"],
            handler=handler,
            pilot=ActorRef(kind="external_pilot", entity=actor.id),
            controller=actor.controller,
            base=site.id,
            cell=site.cell,
        ),
    )


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Attack, ...]:
    uid = str(viewer.user_id)
    sheet = state.sheets.get(uid)
    return tuple(
        x
        for x in rules.attacks(state)
        if viewer.user_id == x.controller
        or (x.handler.entity == uid and same_handler_body(state, x.handler))
        or (
            sheet is not None
            and any(
                actor.entity == uid and actor.incarnation == sheet.character_id
                for actor in x.defenders
            )
        )
    )


class FoundationAttackService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Attack:
        case = next((x for x in visible(state, viewer) if x.id == identity), None)
        if case is None:
            raise WorkflowError("The original attack belongs to its actual participants")
        return case

    def _interceptions(
        self, c: Connection, state: GameState, case: rules.Attack
    ) -> tuple[str, ...]:
        if case.cast is None or not case.defenders:
            return ()
        table = t.m2["m2_actions"]
        defenders = {x.entity: x for x in case.defenders}
        actions = c.execute(
            sa.select(table.c.id, table.c.actor_id).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == case.cast.id,
                table.c.state == "complete",
                table.c.actor_id.in_(tuple(defenders)),
            )
        ).all()
        return tuple(
            event
            for action, owner in actions
            if (
                event := completed_interception(
                    self.game,
                    c,
                    state,
                    self.game.action(c, action),
                    defender=defenders[owner],
                    opponent=case.pilot,
                    scene=case.cast.id,
                    after=case.attempt,
                )
            )
            is not None
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            options: tuple[tuple[str, str], ...] = ()
            if not case.resolution:
                if case.attempt is None and viewer.user_id == case.controller:
                    options = (("attempt", "Attempt to destroy this base"),)
                elif case.attempt is not None and str(viewer.user_id) == case.handler.entity:
                    options = (
                        (("averted", "Verify the completed interception"),)
                        if self._interceptions(c, state, case)
                        else (("destroyed", "Confirm the successful destruction"),)
                    )
            return dict(
                revision=state.revision,
                choices=options,
                account=case.account,
                attempted=bool(case.attempt),
                result=case.result,
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        decision: str,
        account: str,
    ) -> dict[str, Any]:
        account = account.strip()
        if not 0 < len(account) <= 1200:
            raise WorkflowError("Describe the actual attempt or ruling")

        def authorize(c: Connection) -> None:
            for scope in ("world", "strain"):
                self.strain.missions.access.authorize(c, viewer, scope)
            self.game.unpaused(c)
            self._case(load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_quadrant_loss import materialize_loss
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, revision)
            case = self._case(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            period = self.strain.periods._get(c, case.period)
            if (
                case.resolution
                or row["state"] != "pending"
                or period.phase != "preparing"
                or row["off_duty_id"] != case.period
                or row["owner_id"] != case.handler.entity
                or body.get("rule_id") != rules.RULE
                or body.get("foundation_attack_requested") != case.source
                or not same_handler_body(state, case.handler)
            ):
                raise WorkflowError(
                    "Recover the exact saved Foundation attack and preparing period"
                )
            event = str(uuid4())
            changed = GameState.model_validate_json(state.model_dump_json())
            loss = None
            interception = None
            if decision == "attempt":
                actor = rules.pilot(state, case.pilot.entity)
                cast = _cast(self.game, c, state, channel)
                physical = resolve(state, case.pilot, ())
                if (
                    case.attempt is not None
                    or viewer.user_id != case.controller
                    or actor.controller != viewer.user_id
                    or cast is None
                    or not any(
                        x.actor == case.pilot and x.controller == case.controller
                        for x in cast.roles
                    )
                    or physical.cell != case.cell
                    or not physical.piloting
                    or require_base(state, case.base).cell != case.cell
                ):
                    raise WorkflowError(
                        "Only the original piloting actor can attack in the actual base scene"
                    )
                bound = profiles(c, self.store.campaign_id)
                defenders = tuple(
                    x.actor
                    for x in cast.roles
                    if x.actor.kind == "pilot"
                    and x.actor.entity == str(x.controller)
                    and x.controller != case.controller
                    and period.character_ids.get(x.actor.entity) == x.actor.incarnation
                    and x.actor.entity not in period.ended_characters
                    and resolve(state, x.actor, bound, require_current_profile=False).cell
                    == case.cell
                )
                rules.save(
                    changed,
                    case.model_copy(
                        update=dict(
                            cast=cast,
                            defenders=defenders,
                            attempt=event,
                            account=account,
                        )
                    ),
                )
            else:
                judge, appointment = MedicalService(self.store)._handler(c)
                if (
                    viewer.user_id != judge
                    or str(judge) != case.handler.entity
                    or not case.attempt
                    or case.cast is None
                    or decision not in ("destroyed", "averted")
                ):
                    raise WorkflowError(
                        "Only the original human referee resolves this actual attack"
                    )
                intercepts = self._interceptions(c, state, case)
                if decision == "averted":
                    if not intercepts:
                        raise WorkflowError(
                            "Finish an actual original interception before averting the attack"
                        )
                    interception = intercepts[0]
                else:
                    if intercepts:
                        raise WorkflowError(
                            "The original completed interception averted this attack"
                        )
                    actor = rules.pilot(state, case.pilot.entity)
                    physical = resolve(state, case.pilot, ())
                    if (
                        actor.controller != case.controller
                        or not HandlerService(self.store)._member(c, case.controller)
                        or not physical.piloting
                        or physical.cell != case.cell
                        or require_base(state, case.base).cell != case.cell
                        or changed.world is None
                        or changed.strain is None
                    ):
                        raise WorkflowError("The original attacker and base must still be in reach")
                    result = destroy(changed.world, case.base, gorgon_cause=False)
                    if not any(x.kind == "budget_structure_destroyed" for x in result.followups):
                        raise WorkflowError("Resolve the original site's active protection first")
                    changed.world = result.world
                    changed.strain = changed.strain.model_copy(
                        update=dict(
                            triggers=changed.strain.triggers
                            + (
                                Trigger(
                                    id=identity + ":destroyed",
                                    kind="structure_destroyed",
                                    entity=case.base,
                                    source_event=event,
                                ),
                            ),
                        )
                    )
                    loss = stage_loss(
                        state,
                        changed,
                        source=identity,
                        event=event,
                        judge=judge,
                        appointment=appointment,
                        handler=case.handler,
                    )
                rules.save(changed, case.model_copy(update=dict(resolution=event, result=decision)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.foundation_base_attack",
                changed,
                event_id=event,
                work_id=identity,
                decision=decision,
                interception=interception,
            )
            if decision != "attempt":
                self.strain._save(
                    c, row, event, body | dict(attack_outcome=decision), resolved=True
                )
            if loss is not None:
                materialize_loss(self.game, c, loss, event, period=period.id)
            return dict(id=identity, decision=decision)

        return self.strain.missions._write(
            viewer,
            key,
            "m3.foundation_base_attack",
            dict(
                id=identity, revision=revision, channel=channel, decision=decision, account=account
            ),
            operation,
            authorize,
        )
