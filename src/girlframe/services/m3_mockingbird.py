"""Real owned Mockingbird roll decisions and deferred, source-proved Void consequences."""

import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_mockingbird as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_dive import resources
from girlframe.engine.m3_void import FINAL, start_threshold
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def actor(action: dict[str, Any]) -> ActorRef | None:
    data = action["data"]
    if data.get("actor_basic"):
        return ActorRef.model_validate(data["actor_basic"]["ref"])
    for name in ("defeat", "dive", "enforcement", "battle", "engage", "harpy_defeat"):
        if data.get(name, {}).get("actor"):
            return ActorRef.model_validate(data[name]["actor"])
    character = data.get("character_ids", {}).get(str(action["actor_id"]))
    if character:
        return ActorRef(kind="pilot", entity=str(action["actor_id"]), incarnation=character)
    return None


def _copy(state: GameState, changed: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(changed, name))


def released(game: "GameService") -> bool:
    from girlframe.services.m3_access import load_registry

    approval = game.store.policy.m3_approval
    if approval is None or "plays" not in approval.subsystems:
        return False
    try:
        load_registry().require_available(rules.RISK)
    except ValueError:
        return False
    return True


def intercept_results(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    data = action["data"]
    if not released(game) or data.get("adjudication") or not data.get("receipt"):
        return False
    meta = data.get("risk_factor")
    if meta is not None:
        return bool(meta["state"] == "pending")
    ref = actor(action)
    if ref is None or not rules.owns(state, ref, rules.RISK):
        return False
    actual, _ = resources(state, ref)
    eligible = [x.id for x in actual if not x.void]
    if not eligible:
        data["risk_factor"] = dict(state="unavailable", actor=ref.model_dump(mode="json"))
        return False
    data["risk_factor"] = dict(
        state="pending",
        actor=ref.model_dump(mode="json"),
        before=data["result"]["total"],
        receipt=data["receipt"]["id"],
        eligible=eligible,
        followups=[],
    )
    action["state"] = "awaiting_choices"
    game.request(c, action, int(action["actor_id"]), "mockingbird_risk")
    return True


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    meta = action["data"]["risk_factor"]
    if request["kind"] == "mockingbird_void_threshold":
        return dict(work_id=json.loads(request["body_json"])["work_id"])
    if request["kind"] != "mockingbird_risk" or meta["state"] != "pending":
        raise WorkflowError("Recover the original owned Mockingbird decision")
    ref = ActorRef.model_validate(meta["actor"])
    actual, _ = resources(state, ref)
    from girlframe.services.m3_janus_storage import available as storage_available

    return dict(
        storage_available=storage_available(game, c, state, ref),
        total=meta["before"],
        assets=[
            dict(id=x.id, label=getattr(x, "label", getattr(x, "name", x.id)), family=x.family)
            for x in actual
            if not x.void and x.id in meta["eligible"]
        ],
    )


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    if request["kind"] != "mockingbird_risk":
        raise WorkflowError("Finish the real Void consequence; an acknowledgment cannot dismiss it")
    meta = action["data"]["risk_factor"]
    ref = ActorRef.model_validate(meta["actor"])
    if (
        meta["state"] != "pending"
        or str(request["actor_id"]) != str(action["actor_id"])
        or meta["receipt"] != action["data"]["receipt"]["id"]
        or not rules.owns(state, ref, rules.RISK)
        or answer.options
        or answer.denied
        or answer.member is not None
        or answer.flag is not None
    ):
        raise WorkflowError("Only the original owner chooses this actual roll's unused Risk Factor")
    if answer.number is None:
        if answer.fields or answer.text:
            raise WorkflowError("Decline without selecting a cost or replacement total")
        meta["state"] = "declined"
    else:
        if (
            set(answer.fields) not in ({"asset"}, {"asset", "storage"})
            or answer.fields["asset"] not in meta["eligible"]
            or answer.fields.get("storage", "yes") != "yes"
        ):
            raise WorkflowError("Choose one original eligible uncorrupted owned Asset")
        event = action["data"]["response_event"]
        from girlframe.services.m3_janus_storage import gain_source

        changed, followups, payment = rules.risk(
            state,
            profiles(c, game.store.campaign_id),
            ref,
            action["id"],
            event,
            answer.fields["asset"],
            answer.text,
            meta["before"],
            answer.number,
            piloting=bool(action["data"].get("prepared", {}).get("piloting")),
            storage=gain_source(
                game, c, state, ref, request["id"], "mockingbird_risk", "storage" in answer.fields
            ),
        )
        _copy(state, changed)
        meta.update(state="paid", payment=payment.model_dump(mode="json"), choice=request["id"])
        action["data"]["modifiers"].append(
            dict(
                source=rules.RISK,
                amount=answer.number - meta["before"],
                actor=int(action["actor_id"]),
            )
        )
        existing = next(
            (x for x in state.void_thresholds if x.actor == ref and x.stage not in FINAL), None
        )
        if existing is not None:
            # The actual parent Keep already resists this exact original threshold. No new child.
            meta["covered_threshold"] = existing.id
        else:
            for item in followups:
                family: Literal["girl", "frame"] = (
                    "girl" if item.kind == "girl_void_threshold" else "frame"
                )
                identity = str(
                    uuid5(NAMESPACE_URL, "girlframe:risk:" + action["id"] + ":" + family)
                )
                body = dict(
                    id=identity,
                    owner=ref.model_dump(mode="json"),
                    character=ref.incarnation,
                    source_action=action["id"],
                    source_choice=request["id"],
                    source_event=event,
                    source_pdf=19,
                    immediate=True,
                    reason="mockingbird_risk",
                    details=dict(family=family),
                )
                changed, threshold = start_threshold(
                    state,
                    profiles(c, game.store.campaign_id),
                    ref,
                    family,
                    event,
                    identity,
                    source_action=action["id"],
                )
                _copy(state, changed)
                body["threshold"] = threshold.id
                meta["followups"].append(body)
    from girlframe.services.m2_choices import ChoiceEngine

    if action["data"].get("actor_basic"):
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).results(c, action, state=state)
    elif action["data"].get("harpy_defeat"):
        from girlframe.services.m3_harpy_defeat import HarpyDefeatService

        HarpyDefeatService(game.store, game)._results(c, action)
    else:
        ChoiceEngine(game).results(c, state, action)


def intercept_finish(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    meta = action["data"].get("risk_factor")
    if meta is None or meta.get("state") != "paid":
        return False
    for item in meta["followups"]:
        if item.get("completed_event"):
            continue
        if "continuation" not in item:
            game.request(
                c,
                action,
                int(action["actor_id"]),
                "mockingbird_void_threshold",
                dict(work_id=item["id"]),
            )
            item["continuation"] = next(
                x["id"]
                for x in game.pending(c, action["id"])
                if x["kind"] == "mockingbird_void_threshold"
                and json.loads(x["body_json"])["work_id"] == item["id"]
            )
        return True
    return False


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    meta = action["data"].get("risk_factor")
    if meta is None:
        return
    table = t.m3["m3_required_work"]
    for item in meta.get("followups", ()):
        if "continuation" not in item or c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == game.store.campaign_id, table.c.id == item["id"]
            )
        ):
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            item["id"],
            int(action["actor_id"]),
            int(action["actor_id"]),
            "void_threshold",
            item,
            item["source_event"],
        )


def prove_void_source(
    game: "GameService", c: Connection, first: dict[str, Any], body: dict[str, Any], ref: ActorRef
) -> None:
    action = game.action(c, body["source_action"])
    meta = action["data"]["risk_factor"]
    actual = next(x for x in meta["followups"] if x["id"] == first["id"])
    if (
        any(body.get(k) != actual.get(k) for k in actual if k != "completed_event")
        or meta["actor"] != ref.model_dump(mode="json")
        or first["event_id"] != meta["payment"]["event"]
        or first["owner_id"] != ref.entity
        or first["subject_id"] != ref.entity
    ):
        raise ValueError("The actual original Risk payment and consequence must match")
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == first["event_id"],
        )
    )
    saved = GameState.model_validate_json(raw) if raw else None
    payment = rules.RiskPayment.model_validate(meta["payment"])
    fact = dict(
        kind="mockingbird_risk_paid",
        action=action["id"],
        event=payment.event,
        actor=ref.model_dump_json(),
        body=payment.model_dump_json(),
    )
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == first["event_id"]
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(audit["payload_json"]) if audit else {}
    if (
        saved is None
        or fact not in saved.facts
        or audit is None
        or audit["actor_id"] != str(action["actor_id"])
        or payload.get("action_id") != action["id"]
        or payload.get("choice_id") != meta["choice"]
    ):
        raise ValueError("Recover the authenticated actual Risk payment event")


def complete_void_continuation(
    game: "GameService",
    c: Connection,
    work_id: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    row = (
        c.execute(
            sa.select(t.m3["m3_required_work"])
            .where(
                t.m3["m3_required_work"].c.campaign_id == game.store.campaign_id,
                t.m3["m3_required_work"].c.id == work_id,
            )
            .order_by(t.m3["m3_required_work"].c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["state"] != "resolved":
        raise WorkflowError("Finish the actual original Void threshold")
    body = json.loads(row["body_json"])
    action = game.action(c, body["source_action"])
    item = next(x for x in action["data"]["risk_factor"]["followups"] if x["id"] == work_id)
    state = load_state(c, game.store.campaign_id)
    if not any(work_id in x.source_works and x.stage in FINAL for x in state.void_thresholds):
        raise WorkflowError("Recover the actually completed original threshold")
    table = t.m2["m2_choices"]
    c.execute(
        table.update()
        .where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == item["continuation"],
            table.c.state == "pending",
        )
        .values(state="completed_by_work", revision=table.c.revision + 1)
    )
    item["completed_event"] = event
    from girlframe.services.m2_choices import ChoiceEngine

    if not game.pending(c, action["id"]):
        ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)
    from girlframe.services.m3_play_support import sync_finished_roll

    if (
        action["data"].get("m3")
        and action["state"] == "complete"
        and not action["data"]["risk_factor"].get("period_roll_synced")
    ):
        sync_finished_roll(game, c, action, event)
