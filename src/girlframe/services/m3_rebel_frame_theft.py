"""The rolled theft changes only the original Frame after the actual scene resolves."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_frame_theft as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.rolls import IndexSource
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_engage import completed_interception
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
    thief: str,
    narrative: str,
    selector: IndexSource,
    rng_source: Literal["os", "test_injected"],
) -> None:
    site = rules.base(state, base)
    rebel = rules.thief(state, thief, site.cell)
    handler = active_handler(state)
    period = strain.periods._get(c, row["off_duty_id"])
    members = HandlerService(strain.store)
    if (
        handler is None
        or not members._member(c, rebel.controller)
        or any(x.id == row["id"] for x in rules.thefts(state))
    ):
        raise WorkflowError("Recover the original period and actual Rebel controller")
    eligible = rules.population(
        state,
        tuple(
            ActorRef(kind="pilot", entity=owner, incarnation=character)
            for owner, character in period.character_ids.items()
            if owner not in period.ended_characters
            and int(owner) != rebel.controller
            and members._member(c, int(owner))
        ),
        site,
    )
    if not eligible:
        raise WorkflowError("Recover an original available unoccupied Frame before drawing")
    rules.save(
        state,
        rules.Theft(
            id=row["id"],
            source=source,
            period=period.id,
            handler=handler,
            thief=ActorRef(kind="external_pilot", entity=rebel.id),
            controller=rebel.controller,
            base=site.id,
            cell=site.cell,
            population=eligible,
            index=selector.choose(len(eligible)),
            rng_source=rng_source,
            case_account=narrative,
        ),
    )


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Theft, ...]:
    uid = str(viewer.user_id)
    sheet = state.sheets.get(uid)
    return tuple(
        x
        for x in rules.thefts(state)
        if viewer.user_id == x.controller
        or uid == x.handler.entity
        and same_handler_body(state, x.handler)
        or x.attempt is not None
        and sheet is not None
        and any(
            actor.entity == uid and actor.incarnation == sheet.character_id
            for actor in (x.frame.owner, *x.defenders)
        )
    )


def choices(case: rules.Theft, viewer: GuildViewer) -> tuple[tuple[str, str], ...]:
    if case.stopped_by or case.returned:
        return ()
    if case.lost:
        if viewer.user_id == case.controller and case.return_offer is None:
            return (("return", "Offer to return the original Frame"),)
        if case.frame.owner.entity == str(viewer.user_id) and case.return_offer:
            return (("recover", "Recover your actual Frame"),)
        return ()
    if case.attempt is None:
        return (
            (("attempt", "Make the original attempt"),) if viewer.user_id == case.controller else ()
        )
    if case.handler.entity == str(viewer.user_id) and {x.girl for x in case.passes} == set(
        case.defenders
    ):
        return (("lose", "Record the original Frame as lost"),)
    if any(x.entity == str(viewer.user_id) for x in case.defenders):
        if not any(x.girl.entity == str(viewer.user_id) for x in case.passes):
            return (("pass", "Let the original thief go"),)
    return ()


class TheftService:
    def __init__(self, strain: StrainService):
        self.strain, self.game, self.store = strain, strain.game, strain.store

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Theft:
        case = next((x for x in visible(state, viewer) if x.id == identity), None)
        if case is None:
            raise WorkflowError("This theft belongs to its actual original participants")
        return case

    def _scene(
        self, c: Connection, state: GameState, case: rules.Theft, channel: int
    ) -> tuple[SceneCast, tuple[ActorRef, ...]]:
        cast = _cast(self.game, c, state, channel)
        period = self.strain.periods._get(c, case.period)
        if cast is None or not any(
            x.actor == case.thief and x.controller == case.controller for x in cast.roles
        ):
            raise WorkflowError("Join the actual original Rebel and affected people in this scene")
        bindings = profiles(c, self.store.campaign_id)
        joined = tuple(
            x.actor
            for x in cast.roles
            if x.actor.kind == "pilot"
            and x.controller == int(x.actor.entity)
            and x.controller != case.controller
            and period.character_ids.get(x.actor.entity) == x.actor.incarnation
            and x.actor.entity not in period.ended_characters
            and resolve(state, x.actor, bindings, require_current_profile=False).cell == case.cell
        )
        if case.frame.owner not in joined:
            raise WorkflowError(
                "The original owner must be present to see their Frame being stolen"
            )
        return cast, joined

    def _interception(
        self, c: Connection, state: GameState, owner: int, case: rules.Theft, action: dict[str, Any]
    ) -> str | None:
        original = next((x for x in case.defenders if x.entity == str(owner)), None)
        if case.cast is None or original is None:
            return None
        return completed_interception(
            self.game,
            c,
            state,
            action,
            defender=original,
            opponent=case.thief,
            scene=case.cast.id,
            after=case.attempt,
        )

    def _stops(
        self, c: Connection, state: GameState, case: rules.Theft, owner: int
    ) -> tuple[tuple[str, str], ...]:
        if case.cast is None or case.lost or case.stopped_by:
            return ()
        table = t.m2["m2_actions"]
        actions = c.scalars(
            sa.select(table.c.id).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.actor_id == str(owner),
                table.c.scene_id == case.cast.id,
                table.c.state == "complete",
            )
        )
        return tuple(
            (action, "Use completed interception " + action[:8])
            for action in actions
            if self._interception(c, state, owner, case, self.game.action(c, action))
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            know_frame = viewer.user_id == case.controller or case.attempt is not None
            return dict(
                revision=state.revision,
                choices=choices(case, viewer),
                stops=self._stops(c, state, case, viewer.user_id),
                frame=case.frame.instance if know_frame else None,
                account=case.attempt_account,
                lost=bool(case.lost),
                stopped=bool(case.stopped_by),
                returned=bool(case.returned),
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        decision: str,
        *,
        account: str = "",
        action: str | None = None,
    ) -> dict[str, Any]:
        account = account.strip()
        if (decision == "stop") != (action is not None) or (
            action is None and not 0 < len(account) <= 1200
        ):
            raise WorkflowError(
                "Record the actual choice or choose an original completed interception"
            )

        def authorize(c: Connection) -> None:
            for scope in ("world", "strain"):
                self.strain.missions.access.authorize(c, viewer, scope)
            self.game.unpaused(c)
            self._case(load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, revision)
            case = self._case(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            period = self.strain.periods._get(c, case.period)
            recovering = decision in ("return", "recover")
            if (
                row["off_duty_id"] != case.period
                or row["owner_id"] != case.handler.entity
                or body.get("rule_id") != rules.RULE
                or body.get("theft_requested") != case.source
                or not same_handler_body(state, case.handler)
                or case.returned
                or case.stopped_by
                or (
                    row["state"] != "resolved"
                    if recovering
                    else row["state"] != "pending" or period.phase != "preparing"
                )
            ):
                raise WorkflowError(
                    "Recover the exact original recorded theft before changing its outcome"
                )
            event = str(uuid4())
            if decision != "stop" and decision not in {x[0] for x in choices(case, viewer)}:
                raise WorkflowError("Only the original person owns this theft choice")
            if decision in ("attempt", "lose", "return", "recover"):
                rebel = rules.thief(state, case.thief.entity, case.cell)
                if rebel.controller != case.controller or not HandlerService(self.store)._member(
                    c, case.controller
                ):
                    raise WorkflowError("Recover the actual original Rebel controller")
            if decision == "attempt":
                cast, defenders = self._scene(c, state, case, channel)
                available = rules.population(
                    state, (case.frame.owner,), rules.base(state, case.base), reserved_for=case.id
                )
                if case.frame not in available:
                    raise WorkflowError(
                        "The original selected Frame is no longer available at the base"
                    )
                updated = case.model_copy(
                    update=dict(
                        cast=cast, defenders=defenders, attempt=event, attempt_account=account
                    )
                )
            elif decision == "pass":
                original = next(x for x in case.defenders if x.entity == str(viewer.user_id))
                if self._stops(c, state, case, viewer.user_id):
                    raise WorkflowError("Record the actual completed interception first")
                updated = case.model_copy(
                    update=dict(
                        passes=(
                            *case.passes,
                            rules.Pass(girl=original, source=event, account=account),
                        )
                    )
                )
            elif decision == "stop":
                assert action is not None
                proof = self._interception(
                    c, state, viewer.user_id, case, self.game.action(c, action)
                )
                if proof is None:
                    raise WorkflowError(
                        "Use the original Girl's completed interception against this thief"
                    )
                updated = case.model_copy(update=dict(stopped_by=proof))
            elif decision == "lose":
                members = HandlerService(self.store)
                for original in case.defenders:
                    current = state.sheets.get(original.entity)
                    owner = int(original.entity)
                    if (
                        current is None
                        or current.character_id != original.incarnation
                        or not members._member(c, owner)
                        or self._stops(c, state, case, owner)
                    ):
                        raise WorkflowError(
                            "Recover the original responders and any actual interruption first"
                        )
                rules.position(state, case, event, None)
                updated = case.model_copy(update=dict(lost=event, loss_account=account))
            elif decision == "return":
                rules.base(state, case.base)
                updated = case.model_copy(update=dict(return_offer=event, return_account=account))
            else:
                rules.base(state, case.base)
                recovering_owner = resolve(
                    state,
                    case.frame.owner,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if recovering_owner.cell != case.cell or recovering_owner.custody not in (
                    None,
                    "free",
                ):
                    raise WorkflowError(
                        "Recover your real original Frame in person at the original base"
                    )
                rules.position(state, case, event, case.cell)
                updated = case.model_copy(update=dict(returned=event, recovery_account=account))
            rules.save(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.rebel_frame_theft",
                state,
                event_id=event,
                work_id=identity,
                decision=decision,
            )
            if decision in ("stop", "lose"):
                self.strain._save(c, row, event, body | dict(theft_outcome=decision), resolved=True)
            return dict(id=identity, decision=decision)

        return self.strain.missions._write(
            viewer,
            key,
            "m3.rebel_frame_theft",
            dict(
                id=identity,
                revision=revision,
                channel=channel,
                decision=decision,
                account=account,
                action=action,
            ),
            operation,
            authorize,
        )
