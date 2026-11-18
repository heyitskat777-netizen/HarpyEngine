"""Original Director orders and Handler-authored civic outcomes."""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_civic_directive as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class CivicService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Directive:
        result = next(
            (
                x
                for x in rules.cases(state)
                if x.id == identity and viewer.user_id in (x.controller, int(x.handler.entity))
            ),
            None,
        )
        if result is None:
            raise WorkflowError("This civic directive belongs to the original participants")
        return result

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            factions = (
                [(x.id, x.name) for x in state.world.factions if x.active and x.kind == "rebel"]
                if state.world and case.rule == rules.SUPPORT and not case.order
                else []
            )
            return dict(
                rule=case.rule,
                revision=state.revision,
                city=case.city,
                faction=case.faction,
                order=case.order,
                action=case.action,
                can_order=(case.controller == viewer.user_id and case.order_event is None),
                can_act=(
                    str(viewer.user_id) == case.handler.entity
                    and case.order_event is not None
                    and case.action_event is None
                ),
                factions=factions if case.controller == viewer.user_id else [],
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        account: str,
        *,
        issue: bool,
        faction: str | None = None,
    ) -> dict[str, Any]:
        if not 0 < len(account.strip()) <= 1200 or (faction is not None and not issue):
            raise WorkflowError("Record the actual order or performed public action")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            if issue:
                if (
                    case.controller != viewer.user_id
                    or rules.director(state, case.director).controller != viewer.user_id
                ):
                    raise WorkflowError("Only the original fictional Director's controller orders")
            else:
                if str(viewer.user_id) != case.handler.entity or not same_handler_body(
                    state, case.handler
                ):
                    raise WorkflowError("Only the original addressed Handler can perform this act")
                HandlerService(self.store).authorize(c, viewer)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, expected)
            case = self._case(state, viewer, identity)
            event = str(uuid4())
            if issue:
                row = EffectService(self.strain)._row(c, identity)
                body = json.loads(row["body_json"])
                period = self.strain.periods._get(c, case.period)
                if (
                    case.order_event
                    or row["state"] != "pending"
                    or row["off_duty_id"] != case.period
                    or period.phase != "preparing"
                    or body.get("directive_requested") != case.source_event
                    or body["rule_id"] != case.rule
                    or not same_handler_body(state, case.handler)
                ):
                    raise WorkflowError("Reopen the original pending Director order")
                if case.rule == rules.SUPPORT:
                    if state.world is None or not any(
                        x.id == faction and x.active and x.kind == "rebel"
                        for x in state.world.factions
                    ):
                        raise WorkflowError(
                            "The Director must choose a current active Rebel faction"
                        )
                elif faction is not None:
                    raise WorkflowError("This order concerns the original protest city")
                rules.put(
                    state,
                    case.model_copy(
                        update={
                            "order": account.strip(),
                            "order_event": event,
                            "faction": faction,
                        }
                    ),
                )
                self.game.event(
                    c,
                    viewer.user_id,
                    key,
                    "m3.strain_civic_order_issued",
                    state,
                    event_id=event,
                    work_id=identity,
                )
                self.strain._save(c, row, event, body | {"directive_issued": True}, resolved=True)
                return dict(id=identity, state="awaiting_public_action")
            if case.order_event is None or case.action_event:
                raise WorkflowError("Recover the actual received order and its unfinished action")
            rules.put(
                state, case.model_copy(update={"action": account.strip(), "action_event": event})
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_civic_action_performed",
                state,
                event_id=event,
                work_id=identity,
            )
            return dict(id=identity, state="complete")

        return self.strain.missions._write(
            viewer,
            key,
            "m3.strain_civic_directive",
            dict(id=identity, expected=expected, account=account, issue=issue, faction=faction),
            operation,
            authorize,
        )
