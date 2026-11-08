"""Actual scientific demands become real Observation orders, never recovery waivers."""

from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import GameState, Obligation
from girlframe.engine.m3_actor_state import Model
from girlframe.engine.m3_observation import context, order
from girlframe.engine.m3_off_duty import Period, Progress, clone


class Demand(Model):
    subjects: tuple[Snowflake, ...] = Field(min_length=1, max_length=2)
    hiding: dict[str, bool] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def actual_answers(self) -> "Demand":
        if len(set(self.subjects)) != len(self.subjects) or set(self.hiding) != {
            str(x) for x in self.subjects
        }:
            raise ValueError(
                "Choose one or two distinct Girls and explicitly answer each hiding review"
            )
        return self


def require_orders(state: GameState, demand: Demand, source: str, account: str) -> None:
    if (
        state.handler is None
        or not source
        or not account.strip()
        or len(account) > 1200
        or any(uid not in state.order or str(uid) not in state.sheets for uid in demand.subjects)
    ):
        raise ValueError(
            "Choose actual current Girls and record the Foundation's scientific demand"
        )
    for uid in demand.subjects:
        identity = str(uuid5(NAMESPACE_URL, source + ":scientific-order:" + str(uid)))
        if any(x.id == identity for x in state.obligations):
            raise ValueError("This scientific demand already has its required orders")
        state.obligations.append(
            Obligation(
                id=identity,
                kind="scientific_observation_order",
                owner=state.handler,
                target=uid,
                action=source,
                details={
                    "source_pdf": "150",
                    "hiding": "yes" if demand.hiding[str(uid)] else "no",
                    "account": account.strip(),
                },
            )
        )


def materialize(
    period: Period,
    original: GameState,
    owner: int,
    subject: int,
    source_work: str,
    event: str,
    character_id: str,
) -> tuple[Period, GameState]:
    if period.phase != "preparing" or owner != period.handler or owner != original.handler:
        raise ValueError("Scientific orders belong to the actual current preparation and Handler")
    state = GameState.model_validate_json(original.model_dump_json())
    pending = next(
        (
            x
            for x in state.obligations
            if x.kind == "scientific_observation_order"
            and x.owner == owner
            and x.target == subject
            and x.action == source_work
            and x.state == "pending"
        ),
        None,
    )
    if (
        pending is None
        or subject not in period.pilots
        or not event
        or period.character_ids.get(str(subject)) != character_id
        or str(subject) not in state.sheets
        or state.sheets[str(subject)].character_id not in (None, character_id)
    ):
        raise ValueError("Resume the actual pending scientific order for this Girl")
    progress = period.progress.get(str(subject), Progress())
    if progress.roll is not None or progress.action_id is not None or progress.recovered:
        raise ValueError("A scientific demand cannot overwrite a committed Play or recovery")
    hiding, account = pending.details["hiding"] == "yes", pending.details["account"]
    existing_debts = {
        x.id
        for x in state.obligations
        if x.kind == "void_observation" and x.owner == subject and x.state == "pending"
    }
    if progress.observation is None:
        updated, state = order(
            period, period.revision, owner, subject, state, hiding, account, event
        )
        observation = context(updated, subject)[1]
        if existing_debts:
            science_id = str(uuid5(NAMESPACE_URL, event + ":scientific-cause:" + str(subject)))
            state.obligations.append(
                Obligation(
                    id=science_id, kind="void_observation", owner=subject, action=event, details={}
                )
            )
            observation.obligations = (*observation.obligations, science_id)
        else:
            science_id = observation.obligations[0]
    else:
        updated = clone(period)
        observation = context(updated, subject)[1]
        if not set(observation.obligations) <= existing_debts:
            raise ValueError("Recover the changed existing Observation causes first")
        science_id = str(uuid5(NAMESPACE_URL, event + ":scientific-cause:" + str(subject)))
        state.obligations.append(
            Obligation(
                id=science_id,
                kind="void_observation",
                owner=subject,
                action=event,
                details={"source_pdf": "150", "source_work": source_work, "account": account},
            )
        )
        observation.obligations = (*observation.obligations, science_id)
        observation.suspects_hiding = hiding
        observation.hiding_review_event = event
        updated.revision += 1
    science_cause = next(x for x in state.obligations if x.id == science_id)
    science_cause.details.update(
        source_pdf="150", source_work=source_work, account=account, character_id=character_id
    )
    pending = next(x for x in state.obligations if x.id == pending.id)
    pending.state = "fulfilled"
    pending.details["applied_event"] = event
    pending.details["character_id"] = character_id
    return updated, state
