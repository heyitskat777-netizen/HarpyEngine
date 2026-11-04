"""M3 phase bindings for the shared transactional Play pipeline, not a second RNG."""

import json
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_choices import off_duty_modifier
from girlframe.engine.m3_off_duty import Adjustment, Period, Progress, Roll, clone, ordinary_roll
from girlframe.engine.m3_policy import RULESET
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def periods(game: "GameService") -> OffDutyService:
    return OffDutyService(MissionService(game.store))


def authorize(
    game: "GameService", c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    Access(game.store).authorize(c, viewer, "plays")
    if action is not None:
        approval = game.store.policy.m3_approval
        if approval is None or action["data"]["m3"]["registry"] != approval.registry_sha256:
            raise WorkflowError(
                "M3_POLICY_CHANGED: this saved Play needs explicit policy recovery."
            )
        period = periods(game)._get(c, action["data"]["m3"]["period_id"])
        _character(game, c, period, int(action["actor_id"]))
        from girlframe.services.handler_setup import HandlerService

        if (
            period.phase != "active"
            or period.handler != HandlerService(game.store).current(c)[1].handler_id
        ):
            raise WorkflowError("Recover the changed period or Handler before this saved Play.")


def prepare(
    game: "GameService", c: Connection, viewer: GuildViewer, prepared: PlayInput
) -> dict[str, Any]:
    authorize(game, c, viewer)
    if (
        prepared.play != "go_off_duty"
        or prepared.off_duty_id is None
        or prepared.heat
        or prepared.parent
    ):
        raise WorkflowError("Go Off-Duty uses the actual active period and Status instead of Heat.")
    service = periods(game)
    period = service._get(c, prepared.off_duty_id)
    service._view(c, viewer, period)
    state = load_state(c, game.store.campaign_id)
    if (
        period.phase != "active"
        or viewer.user_id not in period.pilots
        or state.handler != period.handler
    ):
        raise WorkflowError(
            "Finish actual period preparation before making its owned Off-Duty Play."
        )
    _character(game, c, period, viewer.user_id)
    existing = period.progress.get(str(viewer.user_id), Progress())
    if existing.roll is not None or existing.action_id is not None:
        raise WorkflowError("Resume this period's saved Play; it cannot be rolled a second time.")
    if any(
        x.kind == "void_observation" and x.owner == viewer.user_id and x.state == "pending"
        for x in state.obligations
    ):
        raise WorkflowError("Void Observation replaces the ordinary Off-Duty Play.")
    if viewer.user_id not in state.order:
        raise WorkflowError("A current canonical Status position is required.")
    status: Literal["Ace", "Wings", "Dog"] = (
        "Ace"
        if state.order[0] == viewer.user_id
        else "Dog"
        if state.order[-1] == viewer.user_id
        else "Wings"
    )
    approval = game.store.policy.m3_approval
    assert approval is not None
    return {
        "period_id": period.id,
        "status": status,
        "modifier": off_duty_modifier(status),
        "registry": approval.registry_sha256,
        "ruleset": RULESET,
    }


def reserve(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    service = periods(game)
    period = service._get(c, action["data"]["m3"]["period_id"])
    updated = clone(period)
    updated.progress[action["actor_id"]] = Progress(action_id=action["id"])
    updated.revision += 1
    service._save(c, updated, event)


def pre_roll(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    action: dict[str, Any],
    state: GameState,
) -> None:
    authorize(game, c, viewer, action)
    service = periods(game)
    meta = action["data"]["m3"]
    period = service._get(c, meta["period_id"])
    _character(game, c, period, viewer.user_id)
    progress = period.progress.get(action["actor_id"])
    if (
        period.phase != "active"
        or progress is None
        or progress.action_id != action["id"]
        or progress.roll is not None
    ):
        raise WorkflowError("Resume the current period's actual reserved Play.")
    status = (
        "Ace"
        if state.order[0] == viewer.user_id
        else "Dog"
        if state.order[-1] == viewer.user_id
        else "Wings"
    )
    if status != meta["status"] or state.handler != period.handler:
        raise WorkflowError(
            "STALE_STATUS: recover the unrolled action and confirm current Status first."
        )


def _character(game: "GameService", c: Connection, period: Period, actor: int) -> None:
    import sqlalchemy as sa

    from girlframe.database import tables as t

    character = c.scalar(
        sa.select(t.characters.c.id).where(
            t.characters.c.campaign_id == game.store.campaign_id,
            t.characters.c.user_id == str(actor),
        )
    )
    if character is None or period.character_ids.get(str(actor)) != character:
        raise WorkflowError("The character changed; explicitly recover the old period first.")


def save_raw_roll(
    game: "GameService", c: Connection, action: dict[str, Any], state: GameState, event: str
) -> None:
    service = periods(game)
    period = service._get(c, action["data"]["m3"]["period_id"])
    actor = int(action["actor_id"])
    receipt = action["data"]["receipt"]
    updated = ordinary_roll(period, period.revision, actor, state, tuple(receipt["faces"]))
    updated.progress[str(actor)].action_id = action["id"]
    saved = updated.progress[str(actor)].roll
    assert saved is not None
    saved.stage = "tag_window"
    service._save(c, updated, event)


def sync_finished_roll(
    game: "GameService", c: Connection, action: dict[str, Any], event: str
) -> None:
    if not action["data"].get("m3_finished"):
        return
    service = periods(game)
    period = service._get(c, action["data"]["m3"]["period_id"])
    progress = period.progress.get(action["actor_id"])
    if (
        progress is None
        or progress.action_id != action["id"]
        or progress.roll is None
        or progress.roll.stage != "tag_window"
    ):
        raise WorkflowError(
            "The saved roll's period binding changed; explicit recovery is required."
        )
    updated = clone(period)
    raw = progress.roll
    updated.progress[action["actor_id"]].roll = Roll(
        faces=raw.faces,
        modifier=raw.modifier,
        total=action["data"]["result"]["total"],
        source=raw.source,
        stage="choices",
        adjustments=tuple(
            Adjustment.model_validate_json(json.dumps(x)) for x in action["data"]["modifiers"]
        ),
    )
    updated.revision += 1
    service._save(c, updated, event)


def resume(
    game: "GameService", viewer: GuildViewer, key: str, identity: str, expected: int
) -> dict[str, Any]:
    """Restore only the saved decisions and receipt after acknowledged lock release."""
    import sqlalchemy as sa

    from girlframe.database import tables as t

    def access(c: Connection) -> None:
        action = game.action(c, identity)
        if not action["data"].get("m3") or viewer.user_id != int(action["actor_id"]):
            raise WorkflowError("Only the acting Pilot may resume its saved M3 Play.")
        authorize(game, c, viewer, action)

    def operation(c: Connection) -> dict[str, Any]:
        game.unpaused(c)
        action = game.action(c, identity)
        meta = action["data"].get("m3_recovery")
        lock = game.lock(c, action["channel_id"])
        period = periods(game)._get(c, action["data"]["m3"]["period_id"])
        progress = period.progress.get(action["actor_id"])
        state = load_state(c, game.store.campaign_id)
        if (
            action["revision"] != expected
            or action["state"] != "aborted"
            or meta is None
            or meta["root"] != identity
            or action["parent_id"]
            or lock is None
            or lock["state"] != "released"
            or period.phase != "active"
            or state.handler != period.handler
            or progress is None
            or progress.action_id != identity
            or progress.recovered
        ):
            raise WorkflowError(
                "Restore the channel permissions and refresh this saved Play first."
            )
        actions = t.m2["m2_actions"]
        choices = t.m2["m2_choices"]
        # Restore descendants only when they were actually paused with this root.
        children = [
            game.action(c, value)
            for value in c.scalars(
                sa.select(actions.c.id).where(actions.c.campaign_id == game.store.campaign_id)
            )
        ]
        for child in children:
            saved = child["data"].get("m3_recovery")
            if child["state"] != "aborted" or saved is None or saved["root"] != identity:
                continue
            for pending in saved["choices"]:
                result = c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == game.store.campaign_id,
                        choices.c.action_id == child["id"],
                        choices.c.id == pending["id"],
                        choices.c.state == "aborted",
                        choices.c.revision == pending["revision"],
                    )
                    .values(state=pending["state"], revision=pending["revision"] + 1)
                )
                if result.rowcount != 1:
                    raise WorkflowError(
                        "The saved decision changed; explicit recovery is required."
                    )
            del child["data"]["m3_recovery"]
            game.save_action(c, child, state=saved["state"])
        locks = t.m2["m2_locks"]
        c.execute(
            locks.update()
            .where(
                locks.c.campaign_id == game.store.campaign_id,
                locks.c.channel_id == action["channel_id"],
            )
            .values(
                action_id=identity,
                state="acquiring",
                body_json="{}",
                lease_until=0,
                claim_token=None,
            )
        )
        game.event(c, viewer.user_id, key, "m3.play_resumed", action_id=identity)
        return {"action_id": identity, "receipt_preserved": bool(action["data"]["receipt"])}

    return game.store._write(
        viewer,
        key,
        "m3.play_resumed",
        {"action_id": identity, "expected": expected},
        operation,
        auto_audit=False,
        authorize=access,
    )


def cancel_unrolled(
    game: "GameService", viewer: GuildViewer, key: str, identity: str, expected: int
) -> dict[str, Any]:
    """Release a stale reservation only after abort, before any dice/resources exist."""

    def access(c: Connection) -> None:
        action = game.action(c, identity)
        if not action["data"].get("m3") or viewer.user_id != int(action["actor_id"]):
            raise WorkflowError("Only the acting Pilot may cancel its unrolled M3 reservation.")
        authorize(game, c, viewer, action)

    def operation(c: Connection) -> dict[str, Any]:
        game.unpaused(c)
        action = game.action(c, identity)
        service = periods(game)
        period = service._get(c, action["data"]["m3"]["period_id"])
        progress = period.progress.get(action["actor_id"])
        lock = game.lock(c, action["channel_id"])
        if (
            action["revision"] != expected
            or action["state"] != "aborted"
            or "m3_recovery" not in action["data"]
            or action["data"]["receipt"] is not None
            or progress is None
            or progress.roll is not None
            or progress.action_id != identity
            or period.phase != "active"
            or lock is None
            or lock["state"] != "released"
        ):
            raise WorkflowError(
                "Only an aborted, unrolled reservation with restored chat can cancel."
            )
        updated = clone(period)
        del updated.progress[action["actor_id"]]
        updated.revision += 1
        del action["data"]["m3_recovery"]
        game.save_action(c, action)
        event = game.event(c, viewer.user_id, key, "m3.unrolled_cancelled", action_id=identity)
        service._save(c, updated, event)
        return {"action_id": identity, "state": "cancelled_unrolled"}

    return game.store._write(
        viewer,
        key,
        "m3.unrolled_cancelled",
        {"action_id": identity, "expected": expected},
        operation,
        auto_audit=False,
        authorize=access,
    )
