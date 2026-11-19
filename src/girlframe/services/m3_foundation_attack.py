"""An independent Pilot's actual attack against the saved target."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_foundation_attack as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, ActorView
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
    target: str,
    pilot: str,
    *,
    person: str | None = None,
) -> None:
    actor = rules.pilot(state, pilot)
    handler = active_handler(state)
    members = HandlerService(strain.store)
    if (
        handler is None
        or not members._member(c, actor.controller)
        or any(x.id == row["id"] for x in rules.attacks(state))
    ):
        raise WorkflowError("Recover the original Foundation Pilot and preparing period")
    victim = None
    base = None
    if person is None:
        site = require_base(state, target)
        base, cell = site.id, site.cell
    else:
        period = strain.periods._get(c, row["off_duty_id"])
        if person == "handler" and target == handler.entity:
            victim = handler
        elif (
            person == "pilot"
            and target in period.character_ids
            and target in state.sheets
            and target not in period.ended_characters
        ):
            victim = current_ref(state, int(target))
            if victim.kind != "pilot" or victim.incarnation != period.character_ids[target]:
                raise WorkflowError("Recover the original Girl's active body from this period")
        else:
            raise WorkflowError("Choose the actual original Handler or a Girl of this period")
        physical = resolve(
            state, victim, profiles(c, strain.store.campaign_id), require_current_profile=False
        )
        if (
            physical.cell is None
            or physical.offstage_source is not None
            or physical.controller == actor.controller
            or not members._member(c, physical.controller)
        ):
            raise WorkflowError("Recover the independent target's actual occupied square")
        cell = physical.cell
    rules.save(
        state,
        rules.Attack(
            id=row["id"],
            source=source,
            period=row["off_duty_id"],
            handler=handler,
            pilot=ActorRef(kind="external_pilot", entity=actor.id),
            controller=actor.controller,
            base=base,
            cell=cell,
            target=victim,
        ),
    )


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Attack, ...]:
    uid = str(viewer.user_id)
    sheet = state.sheets.get(uid)
    return tuple(
        x
        for x in rules.attacks(state)
        if viewer.user_id == x.controller
        or (x.handler.entity == uid and (same_handler_body(state, x.handler) or x.strike))
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

    def _target(self, c: Connection, state: GameState, case: rules.Attack) -> ActorView | None:
        if case.target is None:
            return None
        target = resolve(
            state, case.target, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if target.cell != case.cell or target.offstage_source is not None:
            raise WorkflowError("The original person must still be present in the attack square")
        return target

    def _withdrawal(self, c: Connection, state: GameState, case: rules.Attack) -> str | None:
        if case.target is None or case.attempt is None:
            return None
        target = resolve(
            state, case.target, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if target.cell is None or target.cell == case.cell or target.offstage_source is not None:
            return None
        if case.target.kind == "pilot":
            movement = next(
                (x.source_event for x in state.placements if x.actor == case.target), None
            )
        else:
            movement = next(
                (
                    x["event"]
                    for x in reversed(state.facts)
                    if x.get("kind") == "ordinary_handler_movement"
                    and ActorRef.model_validate_json(x["actor"]) == case.target
                ),
                None,
            )
        if movement is None:
            return None
        events = t.events
        attempt = events.alias()
        return c.scalar(
            sa.select(events.c.id)
            .join(attempt, attempt.c.campaign_id == events.c.campaign_id)
            .where(
                events.c.campaign_id == self.store.campaign_id,
                events.c.id == movement,
                events.c.kind == "m3.physical_moved",
                events.c.actor_id == str(target.controller),
                attempt.c.id == case.attempt,
                events.c.seq > attempt.c.seq,
            )
        )

    def _strike(
        self,
        c: Connection,
        state: GameState,
        case: rules.Attack,
        channel: int,
        asset: str | None,
        event: str,
    ) -> tuple[GameState, tuple[str, ...]]:
        from girlframe.services.m3_battle import damage_actor

        attacker = rules.pilot(state, case.pilot.entity)
        actor_view = resolve(state, case.pilot, ())
        target = self._target(c, state, case)
        cast = _cast(self.game, c, state, channel)
        present = {(x.actor, x.controller) for x in cast.roles} if cast else set()
        if (
            case.target is None
            or target is None
            or attacker.controller != case.controller
            or not actor_view.piloting
            or actor_view.cell != case.cell
            or cast is None
            or case.cast is None
            or cast.id != case.cast.id
            or (case.pilot, case.controller) not in present
            or (case.target, target.controller) not in present
            or (target.rules == "handler" and asset is not None)
            or (
                target.rules != "handler"
                and not any(
                    x.id == asset and not x.concealed and not x.damaged for x in target.assets
                )
            )
            or not HandlerService(self.store)._member(c, case.controller)
        ):
            raise WorkflowError("Recover the original present combatants and actual target Asset")
        changed, followups = damage_actor(
            self.game,
            c,
            state,
            target=case.target,
            asset_id=asset,
            source_action=None,
            source_work=case.id,
            event=event,
            actor=case.pilot,
            chooser_controller=case.controller,
            occurrence="foundation_strike",
            physical_blow=True,
        )
        rules.save(
            changed,
            case.model_copy(
                update=dict(
                    strike=event,
                    followups=followups,
                    resolution=None if followups else event,
                    result=None if followups else "struck",
                )
            ),
        )
        return changed, followups

    def _followups_done(self, c: Connection, case: rules.Attack) -> bool:
        if not case.strike:
            return False
        work = t.m3["m3_required_work"]
        for identity in case.followups:
            row = c.execute(
                sa.select(work.c.state, work.c.body_json)
                .where(work.c.campaign_id == self.store.campaign_id, work.c.id == identity)
                .order_by(work.c.revision.desc())
                .limit(1)
            ).first()
            if row is None or row.state != "resolved":
                return False
            body = json.loads(row.body_json)
            if (
                case.target is None
                or body.get("source_work") != case.id
                or body.get("owner") != case.target.model_dump(mode="json")
            ):
                raise WorkflowError("Recover the actual original strike consequence")
        return True

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            options: tuple[tuple[str, str], ...] = ()
            assets: tuple[tuple[str, str], ...] = ()
            if not case.resolution:
                if case.attempt is None and viewer.user_id == case.controller:
                    options = (("attempt", "Record the actual attack attempt"),)
                elif case.attempt is not None and str(viewer.user_id) == case.handler.entity:
                    if case.strike:
                        if self._followups_done(c, case):
                            options = (("finish", "Verify the completed strike consequences"),)
                    elif self._interceptions(c, state, case) or self._withdrawal(c, state, case):
                        options = (("averted", "Verify the completed defense or withdrawal"),)
                    elif case.target is None:
                        options = (("destroyed", "Confirm the successful destruction"),)
                    else:
                        try:
                            target = self._target(c, state, case)
                        except (ValueError, WorkflowError):
                            target = None
                        if target is not None:
                            assets = (
                                ()
                                if target.rules == "handler"
                                else tuple((x.id, x.name) for x in target.assets if not x.concealed)
                            )
                            if target.rules == "handler" or assets:
                                options = (("strike", "Rule that the physical strike landed"),)
            return dict(
                revision=state.revision,
                choices=options,
                assets=assets,
                account=case.account,
                attempted=bool(case.attempt),
                target=self._target_label(state, case),
                awaiting_consequences=bool(case.strike and not case.resolution),
                result=case.result,
            )

    def _target_label(self, state: GameState, case: rules.Attack) -> str:
        if case.target is None:
            return "The original Foundation base"
        if case.target.kind == "handler":
            return "The original Handler"
        sheet = state.sheets.get(case.target.entity)
        if sheet is not None and sheet.character_id == case.target.incarnation:
            return sheet.callsign
        return "The original Girl"

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        decision: str,
        account: str,
        asset: str | None = None,
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
                or (not case.strike and not same_handler_body(state, case.handler))
                or (asset is not None and decision != "strike")
            ):
                raise WorkflowError(
                    "Recover the exact saved Foundation attack and preparing period"
                )
            event = str(uuid4())
            changed = GameState.model_validate_json(state.model_dump_json())
            loss = None
            interception = None
            withdrawal = None
            struck = False
            finished = False
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
                    or case.base is not None
                    and require_base(state, case.base).cell != case.cell
                ):
                    raise WorkflowError(
                        "Only the original piloting actor can attack in the actual base scene"
                    )
                victim = self._target(c, state, case)
                if victim is not None and not any(
                    role.actor == case.target and role.controller == victim.controller
                    for role in cast.roles
                ):
                    raise WorkflowError("The original person must join the actual attack scene")
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
            elif decision == "finish":
                if str(viewer.user_id) != case.handler.entity or not self._followups_done(c, case):
                    raise WorkflowError("Finish the actual original strike consequences first")
                rules.save(changed, case.model_copy(update=dict(resolution=event, result="struck")))
                finished = True
            else:
                judge, appointment = MedicalService(self.store)._handler(c)
                if (
                    viewer.user_id != judge
                    or str(judge) != case.handler.entity
                    or not case.attempt
                    or case.cast is None
                    or case.strike is not None
                    or decision not in ("destroyed", "averted", "strike")
                ):
                    raise WorkflowError(
                        "Only the original human referee resolves this actual attack"
                    )
                intercepts = self._interceptions(c, state, case)
                if decision == "averted":
                    withdrawal = self._withdrawal(c, state, case) if not intercepts else None
                    if not intercepts and not withdrawal:
                        raise WorkflowError(
                            "Finish an actual original interception or withdrawal "
                            "before averting the attack"
                        )
                    interception = intercepts[0] if intercepts else None
                elif decision == "strike":
                    if intercepts:
                        raise WorkflowError(
                            "The original completed interception averted this attack"
                        )
                    changed, followups = self._strike(c, state, case, channel, asset, event)
                    struck = True
                    finished = not followups
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
                        or case.base is None
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
                if decision != "strike":
                    rules.save(
                        changed, case.model_copy(update=dict(resolution=event, result=decision))
                    )
                    finished = True
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
                withdrawal=withdrawal,
            )
            if struck:
                from girlframe.services.m3_battle import synchronize_damage

                synchronize_damage(self.game, c, event)
            if finished:
                self.strain._save(
                    c,
                    row,
                    event,
                    body
                    | dict(
                        attack_outcome="struck" if decision in ("strike", "finish") else decision
                    ),
                    resolved=True,
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
            )
            | ({"asset": asset} if asset is not None else {}),
            operation,
            authorize,
        )
