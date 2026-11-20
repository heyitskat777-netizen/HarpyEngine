"""Private work derived from the native mission clock ledger."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.scenes.mission_timing import Clock
from girlframe.services import mission_timing_history as history
from girlframe.services.campaign_time_history import query
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

REVIEWED = "timeline.deadline_reviewed"


def _clock_rows(campaign: str, scene: str) -> sa.Select[Any]:
    return query(campaign, history.EVENT).where(
        sa.func.json_extract(t.events.c.payload_json, "$.clock.scene") == scene
    )


def _item(receipt: str, clock: Clock) -> dict[str, Any]:
    return {
        "source_receipt": receipt,
        "scene_id": clock.scene,
        "clock_id": clock.id,
        "minute": clock.minute,
        "deadline": clock.deadline.minute,
        "boundary": clock.deadline.boundary,
    }


def pending_ruling(c: Connection, campaign: str, scene: str) -> dict[str, Any] | None:
    latest = history.current(c, campaign)
    if latest is None:
        return None
    revision, clock = latest
    ruling = clock.ruling
    if clock.closed or clock.scene != scene or ruling is None:
        return None
    payload = t.events.c.payload_json
    identity = c.scalar(
        _clock_rows(campaign, scene)
        .where(
            sa.func.json_extract(payload, "$.clock.id") == clock.id,
            sa.func.json_extract(payload, "$.transition") == "ruling_required",
        )
        .with_only_columns(t.events.c.id)
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if identity is None:
        raise WorkflowError("TIMING_REVIEW_SOURCE: recover the original pending timing receipt.")
    option = next(
        (item for item in (clock.menu.available if clock.menu else ()) if item.id == ruling.option),
        None,
    )
    attempted = None
    if ruling.proposed_rejoin is not None:
        attempted = ruling.proposed_rejoin.minute
    elif option is not None and option.minutes is not None:
        attempted = clock.minute + option.minutes
    return _item(identity, clock) | {
        "id": "ruling:" + identity,
        "kind": ruling.reason,
        "owner": "handler",
        "clock_revision": revision,
        "option_label": option.label if option else None,
        "attempted_minute": attempted,
        "next_action": "publish_options"
        if ruling.reason == "unknown_duration"
        else "define_consequence",
    }


class DirectorTimingReview:
    def __init__(self, observer: DirectorObservationService, facilitator_id: int | None = None):
        self.observer, self.store = observer, observer.store
        self.facilitator_id = facilitator_id

    def _scope(self, c: Connection, viewer: GuildViewer, scene: str) -> None:
        row = self.observer._scene(c, scene, viewer, allow_closed=True)
        if self.observer.synthetic:
            self.store.administrator(viewer)
            policy = self.observer._state(c, scene)
            if policy.policy.mode != "shadow" or not self.observer._consented(c, row, policy):
                raise WorkflowError("OBSERVATION_DISABLED: retain current scene consent.")
        elif self.facilitator_id == viewer.user_id:
            HandlerService(self.store).authorize(c, viewer)
        else:
            self.store.administrator(viewer)

    def _reviewed(self, campaign: str, scene: str) -> sa.Select[Any]:
        return query(campaign, REVIEWED).where(
            sa.func.json_extract(t.events.c.payload_json, "$.scene_id") == scene
        )

    def _cutoffs(self, scene: str) -> sa.Select[Any]:
        return _clock_rows(self.store.campaign_id, scene).where(
            sa.func.json_extract(t.events.c.payload_json, "$.clock.consequence_receipt")
            == t.events.c.id
        )

    def pending(self, c: Connection, scene: str) -> list[dict[str, Any]]:
        campaign = self.store.campaign_id
        reviewed = t.events.alias("deadline_review")
        rows = c.execute(
            self._cutoffs(scene)
            .where(
                ~sa.exists(
                    sa.select(1)
                    .select_from(reviewed)
                    .where(
                        reviewed.c.campaign_id == campaign,
                        reviewed.c.kind == REVIEWED,
                        sa.func.json_extract(reviewed.c.payload_json, "$.source_receipt")
                        == t.events.c.id,
                    )
                )
            )
            .order_by(t.events.c.seq)
        ).mappings()
        items = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            clock = Clock.model_validate_json(json.dumps(payload["clock"]))
            items.append(
                _item(row["id"], clock)
                | {
                    "id": "cutoff:" + row["id"],
                    "kind": "missed_cutoff",
                    "owner": "gm",
                    "from_minute": payload["from_minute"],
                    "consequence": clock.deadline.consequence,
                    "next_action": "review_recorded_consequence",
                }
            )
        if ruling := pending_ruling(c, campaign, scene):
            items.append(ruling)
        return items

    def view(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._scope(c, viewer, scene)
            return self.pending(c, scene)

    def acknowledge(
        self, viewer: GuildViewer, key: str, scene: str, source_receipt: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._scope(c, viewer, scene)

        def operation(c: Connection) -> dict[str, Any]:
            self.observer.game.unpaused(c)
            if (
                c.scalar(
                    self._cutoffs(scene)
                    .with_only_columns(t.events.c.id)
                    .where(t.events.c.id == source_receipt)
                )
                is None
            ):
                raise WorkflowError(
                    "TIMING_REVIEW_SOURCE: select a committed cutoff in this scene."
                )
            payload = {"scene_id": scene, "source_receipt": source_receipt}
            prior = c.scalar(
                self._reviewed(self.store.campaign_id, scene)
                .with_only_columns(t.events.c.id)
                .where(
                    sa.func.json_extract(t.events.c.payload_json, "$.source_receipt")
                    == source_receipt
                )
            )
            receipt = prior or self.store._audit(c, viewer.user_id, key, REVIEWED, payload)
            return payload | {"receipt": receipt, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            REVIEWED,
            {"scene_id": scene, "source_receipt": source_receipt},
            operation,
            authorize=authorize,
            auto_audit=False,
        )
