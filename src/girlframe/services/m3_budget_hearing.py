"""The printed solo hearing keeps accusation and responses between its two authors."""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_budget_hearing as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_civic_directive import director
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    source: str,
    authority: str,
    owner: int,
) -> None:
    original = director(state, authority)
    period = strain.periods._get(c, row["off_duty_id"])
    handler = active_handler(state)
    if handler is None or owner not in period.pilots or original.controller == owner:
        raise WorkflowError("Choose the original Girl and a separate fictional Director controller")
    girl = current_ref(state, owner)
    members = HandlerService(strain.store)
    if (
        period.character_ids.get(girl.entity) != girl.incarnation
        or girl.entity in period.ended_characters
        or any(x.id == row["id"] for x in rules.hearings(state))
        or not all(members._member(c, user) for user in (owner, original.controller))
        or handler.entity != row["owner_id"]
    ):
        raise WorkflowError("Recover the original preparing period and joined hearing participants")
    rules.save(
        state,
        rules.Hearing(
            id=row["id"],
            period=period.id,
            source=source,
            handler=handler,
            girl=girl,
            director=original.id,
            controller=original.controller,
        ),
    )


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Hearing, ...]:
    result = []
    for case in rules.hearings(state):
        if viewer.user_id == case.controller:
            try:
                if director(state, case.director).controller == viewer.user_id:
                    result.append(case)
            except ValueError:
                continue
        elif case.girl.entity == str(viewer.user_id) and case.notice_event is not None:
            sheet = state.sheets.get(case.girl.entity)
            if sheet is not None and sheet.character_id == case.girl.incarnation:
                result.append(case)
    return tuple(result)


def options(case: rules.Hearing, viewer: GuildViewer) -> tuple[tuple[str, str], ...]:
    if viewer.user_id == case.controller:
        if case.phase == "notice":
            return (("notify", "Serve the accusation"),)
        if case.phase == "finding":
            return (("dismiss", "Withdraw the accusation"), ("refer", "Refer a Severe finding"))
    if case.girl.entity == str(viewer.user_id) and case.phase == "answer":
        return (("answer", "Give your own response"),)
    return ()


class HearingService:
    def __init__(self, strain: StrainService):
        self.strain, self.game, self.store = strain, strain.game, strain.store

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Hearing:
        result = next((x for x in visible(state, viewer) if x.id == identity), None)
        if result is None:
            raise WorkflowError("Only the original parties can reopen this private hearing")
        return result

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            return dict(
                revision=state.revision,
                phase=case.phase,
                charge=case.charge,
                defense=case.defense,
                finding=case.finding,
                options=options(case, viewer),
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: str,
        account: str,
    ) -> dict[str, Any]:
        account = account.strip()
        if not 0 < len(account) <= 1200:
            raise WorkflowError("Record your actual statement in up to 1,200 characters")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            self._case(load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, revision)
            case = self._case(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            period = self.strain.periods._get(c, case.period)
            members = HandlerService(self.store)
            if (
                row["state"] != "pending"
                or row["off_duty_id"] != case.period
                or row["owner_id"] != case.handler.entity
                or body.get("rule_id") != rules.RULE
                or body.get("hearing_requested") != case.source
                or period.phase != "preparing"
                or not same_handler_body(state, case.handler)
                or director(state, case.director).controller != case.controller
                or current_ref(state, int(case.girl.entity)) != case.girl
                or not all(
                    members._member(c, user) for user in (case.controller, int(case.girl.entity))
                )
            ):
                raise WorkflowError("Recover the actual hearing source and both original parties")
            if choice not in {x[0] for x in options(case, viewer)}:
                raise WorkflowError("Only the original speaker can make the current hearing choice")
            event = str(uuid4())
            if choice == "notify":
                updated = case.model_copy(
                    update=dict(phase="answer", charge=account, notice_event=event)
                )
            elif choice == "answer":
                updated = case.model_copy(
                    update=dict(phase="finding", defense=account, answer_event=event)
                )
            else:
                updated = case.model_copy(
                    update=dict(
                        phase="dismissed" if choice == "dismiss" else "review",
                        finding=account,
                        finding_event=event,
                    )
                )
            rules.save(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_hearing_statement",
                state,
                event_id=event,
                work_id=identity,
            )
            if choice in ("dismiss", "refer"):
                self.strain._save(c, row, event, body, resolved=choice == "dismiss")
            return dict(id=identity, phase=updated.phase)

        return self.strain.missions._write(
            viewer,
            key,
            "m3.budget_hearing_statement",
            dict(id=identity, revision=revision, choice=choice, account=account),
            operation,
            authorize,
        )
