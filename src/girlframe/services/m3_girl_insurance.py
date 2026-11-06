"""Genuine advancement acquisition and source-proved next-death Budget relief."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_girl_insurance as rules
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_strain import copy as strain_copy
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    value = next((x for x in rules.acquisitions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the genuine Girl Insurance acquisition")
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    born = next(
        (x for x in rules.acquisitions(_history(c, game, value.event)) if x.id == identity), None
    )
    _, _, handler, appointment, award = HandlerAdvancementService(game.store)._proof(c, value.award)
    if (
        born != value
        or award is None
        or award.acquired_rule != rules.RULE
        or award.acquisition != value.id
        or award.spend_event != value.event
        or (handler, appointment) != (value.handler, value.appointment)
    ):
        raise WorkflowError("Recover the original Handler's actual insurance award spend")
    return value


def _before(game: GameService, c: Connection, event: str) -> GameState:
    sequence = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    history = t.m2["m2_state_history"]
    raw = (
        c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == game.store.campaign_id,
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.seq < sequence,
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        if sequence
        else None
    )
    if raw is None:
        raise WorkflowError("Recover the genuine pre-death insurance source snapshot")
    return GameState.model_validate_json(raw)


def prepare(
    game: GameService, c: Connection, previous: GameState, state: GameState, event: str
) -> None:
    new_deaths = [
        a
        for a in state.career_archives
        if a.source_event == event
        and a.ending in ("death", "execution")
        and not any(x.id == a.id for x in previous.career_archives)
    ]
    if not new_deaths:
        return
    held = [x for x in rules.active(previous) if same_handler_body(previous, x.handler)]
    if not held:
        return
    if len(held) != 1 or previous.strain is None or state.strain is None:
        raise WorkflowError("Recover one actual original Handler insurance and Strain source")
    receipt = paid(game, c, previous, held[0].id)
    archive = new_deaths[0]
    if (
        archive.actor.kind != "pilot"
        or int(archive.actor.entity) not in previous.order
        or archive.actor.entity not in previous.sheets
        or previous.sheets[archive.actor.entity].character_id != archive.actor.incarnation
    ):
        raise WorkflowError("Insure only the next actual original current Cadre Girl death")
    value = rules.Consumption(
        id=receipt.id + ":death",
        acquisition=receipt.id,
        actor=archive.actor,
        archive=archive.id,
        event=event,
        budget_before=previous.strain.levels["budget"],
    )
    rules.put(state, value)
    state.strain = strain_copy(state.strain, levels=state.strain.levels | {"budget": "low"})


def prove_consumption(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Consumption:
    value = next((x for x in rules.consumptions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover this actual single insurance consumption")
    receipt = paid(game, c, state, value.acquisition)
    after = _history(c, game, value.event)
    before = _before(game, c, value.event)
    born = next((x for x in rules.consumptions(after) if x.id == identity), None)
    deaths = [
        a
        for a in after.career_archives
        if a.source_event == value.event
        and a.ending in ("death", "execution")
        and not any(x.id == a.id for x in before.career_archives)
    ]
    if (
        born != value
        or receipt not in rules.active(before)
        or not same_handler_body(before, receipt.handler)
        or before.strain is None
        or after.strain is None
        or before.strain.levels["budget"] != value.budget_before
        or after.strain.levels["budget"] != value.budget_after
        or not deaths
        or (deaths[0].id, deaths[0].actor) != (value.archive, value.actor)
        or int(value.actor.entity) not in before.order
        or before.sheets[value.actor.entity].character_id != value.actor.incarnation
    ):
        raise WorkflowError("Recover the exact genuine original death and actual Budget effect")
    return value


def verify_exclusion(
    game: GameService, c: Connection, state: GameState, event: str, archive_id: str
) -> bool:
    values = [x for x in rules.consumptions(state) if x.event == event and x.archive == archive_id]
    if not values:
        return False
    if len(values) != 1 or not rules.budget_death_excluded(state, event, archive_id):
        raise WorkflowError("Recover the exact actual insured death exclusion")
    prove_consumption(game, c, state, values[0].id)
    return True


def prove_reduction(
    game: GameService, c: Connection, before: GameState, after: GameState, event: str
) -> bool:
    if (
        before.strain is None
        or after.strain is None
        or before.strain.levels["budget"] != "high"
        or after.strain.levels["budget"] != "low"
    ):
        return False
    for value in rules.consumptions(after):
        if value.event == event and value.budget_before == "high":
            prove_consumption(game, c, after, value.id)
            return True
    return False


class GirlInsuranceService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy", director_response=True)
        gate.authorize(c, viewer, "strain", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if identity:
                receipt = paid(self.game, c, state, identity)
                if receipt.handler.entity != str(viewer.user_id):
                    raise WorkflowError("This insurance belongs to its original Handler")
                held = [receipt]
            else:
                HandlerService(self.store).authorize(c, viewer)
                held = [
                    paid(self.game, c, state, x.id)
                    for x in rules.acquisitions(state)
                    if same_handler_body(state, x.handler)
                ]
            records = []
            for receipt in held:
                spent = next(
                    (x for x in rules.consumptions(state) if x.acquisition == receipt.id), None
                )
                if spent:
                    prove_consumption(self.game, c, state, spent.id)
                records.append(
                    dict(
                        id=receipt.id,
                        phase="consumed" if spent else "held",
                        account=receipt.account,
                        death=spent.actor.model_dump(mode="json") if spent else None,
                        archive=spent.archive if spent else None,
                        budget_before=spent.budget_before if spent else None,
                        budget_after=spent.budget_after if spent else None,
                    )
                )
            return dict(
                revision=state.revision,
                owned=any(x["phase"] == "held" for x in records),
                historical=identity is not None,
                records=records,
                awards=HandlerAdvancementService(self.store)._tasks(c, viewer)
                if not identity
                else [],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        spent = {x.acquisition for x in rules.consumptions(state)}
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Girl Insurance — consumed" if x.id in spent else "Girl Insurance — held",
                phase="consumed" if x.id in spent else "held",
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ]

    def buy(
        self, viewer: GuildViewer, key: str, award_id: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _, state, handler, appointment, award = HandlerAdvancementService(self.store)._source(
                c, viewer, award_id
            )
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            if (
                state.strain is None
                or state.revision != revision
                or award is None
                or award.phase != "held"
                or not account.strip()
                or any(same_handler_body(state, x.handler) for x in rules.active(state))
            ):
                raise WorkflowError(
                    "Spend one actual held award on unowned next-death Girl Insurance"
                )
            event = str(uuid4())
            value = rules.Acquisition(
                id="girl-insurance:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            advancement.put(
                state,
                advancement.Award.model_validate_json(
                    award.model_copy(
                        update=dict(
                            phase="spent",
                            acquired_rule=rules.RULE,
                            acquisition=value.id,
                            spend_event=event,
                            spend_account=account.strip(),
                        )
                    ).model_dump_json()
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
            )
            return dict(id=value.id, phase="held")

        return self.store._write(
            viewer,
            key,
            "m3.girl_insurance_acquired",
            dict(award=award_id, revision=revision, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
