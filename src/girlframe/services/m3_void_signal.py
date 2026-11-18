"""One private, original-owner Void alteration, backed by its saved Strain draw."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_void_signal as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_janus_storage import alter, effective_assets, effective_for_owner
from girlframe.engine.rolls import IndexSource
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def stage(
    state: GameState,
    strain: StrainService,
    c: Connection,
    row: dict[str, Any],
    target: str | None,
    event: str,
    selector: IndexSource,
    rng: Literal["os", "test_injected"],
) -> None:
    period = strain.periods._get(c, row["off_duty_id"])
    people = tuple(current_ref(state, uid) for uid in period.pilots)
    if (
        not people
        or any(period.character_ids.get(x.entity) != x.incarnation for x in people)
        or target is None
        or state.world is None
        or not any(x.id == target and x.alive for x in state.world.gorgons)
        or any(x.id == row["id"] for x in rules.signals(state))
    ):
        raise WorkflowError("Recover the original living Gorgon and Off-Duty roster")
    if any(asset.void for actor in people for asset in effective_for_owner(state, actor.entity)):
        raise WorkflowError(
            "UNSUPPORTED_RULE: the existing Void recipients need the actual Gorgon-linked Dive"
        )
    index = selector.choose(len(people))
    if type(index) is not int or not 0 <= index < len(people):
        raise WorkflowError("Invalid draw for the original roster")
    rules.put(
        state,
        rules.Signal(
            id=row["id"],
            source_event=event,
            gorgon=target,
            people=people,
            index=index,
            rng=rng,
        ),
    )


class SignalService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _owned(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Signal:
        record = next((x for x in rules.signals(state) if x.id == identity), None)
        if record is None or record.actor.entity != str(viewer.user_id):
            raise WorkflowError("Only the originally drawn Girl may review her Void gain")
        return record

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            record = self._owned(state, viewer, identity)
            return dict(
                revision=state.revision,
                gain_event=record.gain_event,
                asset=record.asset,
                assets=tuple(
                    (x.id, x.name) for x in effective_assets(state, record.actor) if not x.void
                )
                if record.gain_event is None
                else (),
            )

    def gain(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        asset: str,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            self._owned(load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, expected)
            record = self._owned(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                record.gain_event is not None
                or row["state"] != "pending"
                or body.get("signal_requested") != record.source_event
                or body.get("rule_id") != rules.RULE
                or self.strain.periods._get(c, row["off_duty_id"]).phase != "preparing"
            ):
                raise WorkflowError("Recover the original pending Void gain")
            actor = resolve(
                state,
                record.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if actor.piloting is None or actor.controller != viewer.user_id:
                raise WorkflowError(
                    "Recover the actual original Girl's current body and Frame mode"
                )
            event = str(uuid4())
            changed, follow = alter(
                state,
                record.actor,
                asset,
                account.strip(),
                identity,
                event,
                piloting=actor.piloting,
            )
            families = tuple("girl" if x.kind == "girl_void_threshold" else "frame" for x in follow)
            thresholds = tuple(f"{identity}:signal:{family}" for family in families)
            rules.put(
                changed,
                record.model_copy(
                    update={
                        "asset": asset,
                        "gain_event": event,
                        "thresholds": thresholds,
                    }
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_void_signal_gained",
                changed,
                event_id=event,
                work_id=identity,
            )
            for family, work in zip(families, thresholds, strict=True):
                related(
                    c,
                    self.store,
                    row,
                    work,
                    viewer.user_id,
                    viewer.user_id,
                    "void_threshold",
                    dict(
                        owner=record.actor.model_dump(mode="json"),
                        character=record.actor.incarnation,
                        details=dict(family=family),
                        source_action=None,
                        source_pdf=19,
                        reason=rules.KIND,
                        signal=identity,
                    ),
                    event,
                )
            self.strain._save(
                c,
                row,
                event,
                body | {"signal_gained": event},
                resolved=not thresholds,
            )
            return dict(id=identity, state="pending" if thresholds else "resolved")

        return self.strain.missions._write(
            viewer,
            key,
            "m3.strain_void_signal_gained",
            dict(id=identity, expected=expected, asset=asset, account=account),
            operation,
            authorize,
        )


def prove_threshold(
    c: Connection,
    service: SignalService,
    row: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    identity = body["signal"]
    parent = EffectService(service.strain)._row(c, identity)
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == service.store.campaign_id,
            history.c.event_id == row["event_id"],
        )
    )
    proof = (
        next(
            (x for x in rules.signals(GameState.model_validate_json(raw)) if x.id == identity),
            None,
        )
        if raw
        else None
    )
    if (
        proof is None
        or proof.actor != actor
        or proof.gain_event != row["event_id"]
        or row["id"] not in proof.thresholds
        or row["off_duty_id"] != parent["off_duty_id"]
        or json.loads(parent["body_json"]).get("signal_gained") != row["event_id"]
        or body["details"]["family"] not in ("girl", "frame")
        or row["id"] != f"{identity}:signal:{body['details']['family']}"
    ):
        raise ValueError("Recover the actual gain and original threshold for this Strain effect")


def complete(c: Connection, service: SignalService, identity: str, event: str) -> None:
    row = EffectService(service.strain)._row(c, identity)
    body = json.loads(row["body_json"])
    record = next(
        x for x in rules.signals(load_state(c, service.store.campaign_id)) if x.id == identity
    )
    table = t.m3["m3_required_work"]
    if row["state"] == "pending" and all(
        c.scalar(
            sa.select(table.c.state)
            .where(
                table.c.campaign_id == service.store.campaign_id,
                table.c.id == work,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        == "resolved"
        for work in record.thresholds
    ):
        service.strain._save(c, row, event, body, resolved=True)
