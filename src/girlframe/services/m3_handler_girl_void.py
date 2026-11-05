"""Actual source Girl-rules Handler Void, existing-Asset facts and owned rewriting."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_girl_void as rules
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_handler_girl_void_state import ExistingAsset, HandlerGirlVoid
from girlframe.engine.m3_item_state import HeldItem
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _snapshot(c: Connection, game: "GameService", event: str) -> GameState | None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    return GameState.model_validate_json(raw) if raw else None


def _row(c: Connection, game: "GameService", work: str, *, first: bool = False) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == work)
            .order_by(table.c.revision.asc() if first else table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover this exact Handler Girl Void source work.")
    return dict(row)


def _source(
    c: Connection, game: "GameService", work: str
) -> tuple[GameState, dict[str, Any], HandlerGirlVoid]:
    from girlframe.services.m3_mockingbird_void import prove_handler_girl_void_source

    first, current = _row(c, game, work, first=True), _row(c, game, work)
    body = json.loads(first["body_json"])
    actor = ActorRef.model_validate(body["owner"])
    prove_handler_girl_void_source(game, c, first, body, actor)
    proof = _snapshot(c, game, first["event_id"])
    original = next((x for x in proof.handler_girl_void if x.work == work), None) if proof else None
    state = load_state(c, game.store.campaign_id)
    episode = next((x for x in state.handler_girl_void if x.work == work), None)
    if (
        original is None
        or episode is None
        or original.actor != actor
        or any(
            getattr(original, k) != getattr(episode, k)
            for k in (
                "id",
                "work",
                "actor",
                "body",
                "controller",
                "caster",
                "caster_controller",
                "context_source",
                "source_event",
                "appointment",
                "judge",
                "judge_actor",
            )
        )
        or any(json.loads(current["body_json"]).get(k) != v for k, v in body.items())
    ):
        raise WorkflowError("Recover the immutable actual Handler Girl source context/body.")
    return state, current, episode


def prove_handler_item(
    c: Connection, game: "GameService", state: GameState, item: HeldItem
) -> None:
    """One real owner proposal and factual source-judge review create the sole Item authority."""
    if item.source_owner.kind != "handler" or not item.factual_source_action:
        raise WorkflowError(
            "This actual Handler mechanical Item needs its original factual source."
        )
    _, _, episode = _source(c, game, item.factual_source_action)
    confirmed = _snapshot(c, game, item.source_event)
    proposal_state = _snapshot(c, game, item.proposed_event or "")
    reviewed = (
        next((x for x in confirmed.handler_girl_void if x.id == episode.id), None)
        if confirmed
        else None
    )
    proposed = (
        next((x for x in proposal_state.handler_girl_void if x.id == episode.id), None)
        if proposal_state
        else None
    )
    fact = next((x for x in reviewed.proposals if x.item == item.id), None) if reviewed else None
    before = (
        next((x for x in proposed.proposals if fact and x.id == fact.id), None)
        if proposed
        else None
    )
    events = c.execute(
        sa.select(t.events).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id.in_((item.source_event, item.proposed_event or "")),
        )
    ).mappings()
    audit = {x["id"]: dict(x) for x in events}
    review_event, proposal_event = (
        audit.get(item.source_event),
        audit.get(item.proposed_event or ""),
    )
    initial = (
        next((x for x in confirmed.held_items if x.id == item.id), None) if confirmed else None
    )
    if (
        fact is None
        or before is None
        or fact.state != "accepted"
        or before.state != "proposed"
        or fact.review_event != item.source_event
        or fact.proposal_event != item.proposed_event
        or item.source_owner != episode.actor
        or item.confirmed_controller != episode.judge
        or item.confirmed_by != episode.judge_actor
        or item.confirmed_event != item.source_event
        or fact.asset_json != item.origin_asset_json
        or initial is None
        or initial.asset_json != item.origin_asset_json
        or initial.asset_owner != episode.actor
        or initial.asset_id != item.asset_id
        or item.id != "handler-girl-item:" + fact.id
        or review_event is None
        or proposal_event is None
        or review_event["kind"] != "m3.handler_girl_asset_reviewed"
        or review_event["actor_id"] != str(episode.judge)
        or proposal_event["kind"] != "m3.handler_girl_asset_proposed"
        or proposal_event["actor_id"] != str(episode.controller)
        or confirmed is None
        or len(rules.girl_assets(confirmed, episode.actor)) > 4
    ):
        raise WorkflowError(
            "Recover actual owner facts, source judge review and sole original Asset authority."
        )
    asset = AssetState.model_validate_json(item.origin_asset_json or "{}")
    if (
        asset.family != "girl"
        or asset.void
        or asset.intrinsic is not None
        or asset.name != fact.name
        or asset.description != fact.description
        or asset.damaged != fact.damaged
        or asset.id != "handler-girl:" + fact.id
    ):
        raise WorkflowError(
            "Factual registration cannot invent gear, an Ability or a repaired Asset."
        )


class HandlerGirlVoidService:
    def __init__(self, store: OnboardingStore, game: "GameService | None" = None):
        from girlframe.services.m2_game import GameService

        self.store, self.game = store, game or GameService(store)

    def _owned(
        self,
        c: Connection,
        viewer: GuildViewer,
        work: str,
        *,
        write: bool = False,
        role: str | None = None,
    ) -> tuple[GameState, dict[str, Any], HandlerGirlVoid]:
        if write:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
        else:
            self.game.authorize(c, viewer, game=False)
        state, row, episode = _source(c, self.game, work)
        owners = {
            "patient": episode.controller,
            "caster": episode.caster_controller,
            "judge": episode.judge,
        }
        if (
            viewer.user_id not in owners.values()
            or role is not None
            and viewer.user_id != owners[role]
        ):
            raise WorkflowError(
                "This source belongs to its actual patient, caster or factual judge."
            )
        if write and (
            episode.phase in ("complete", "allure", "ended")
            or MedicalService(self.store)._handler(c)[1] != episode.appointment
            or not same_handler_body(state, episode.actor)
        ):
            raise WorkflowError(
                "Recover the actual original living body and source appointment, not a successor."
            )
        return state, row, episode

    def _authorize(self, c: Connection, viewer: GuildViewer, work: str) -> None:
        Access(self.store).authorize(c, viewer, "plays", director_response=True)
        self._owned(c, viewer, work)

    def _can_act(self, c: Connection, viewer: GuildViewer) -> bool:
        try:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
        except WorkflowError:
            return False
        return True

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for episode in state.handler_girl_void:
            if episode.phase in ("complete", "allure", "ended"):
                continue
            controller = (
                episode.judge
                if episode.phase == "review"
                else episode.caster_controller
                if episode.phase == "asset"
                else episode.controller
            )
            if controller != viewer.user_id:
                continue
            _source(c, self.game, episode.work)
            result.append(
                dict(
                    id=episode.work,
                    kind="handler_girl_void",
                    state=episode.phase,
                    can_act=self._can_act(c, viewer),
                    label={
                        "facts": "Describe an actual existing Handler Girl Asset",
                        "review": "Review source-owned existing Asset facts",
                        "asset": "Choose the actual counterpart Asset gaining Void",
                        "rewrite": "Rewrite your actual chosen Asset with Void",
                    }[episode.phase],
                )
            )
        return result

    def get(self, viewer: GuildViewer, work: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, row, episode = self._owned(c, viewer, work)
            controller = (
                episode.judge
                if episode.phase == "review"
                else episode.caster_controller
                if episode.phase == "asset"
                else episode.controller
            )
            proposal = (
                episode.proposals[-1].model_dump(mode="json")
                if (episode.proposals and viewer.user_id in (episode.judge, episode.controller))
                else None
            )
            return dict(
                id=work,
                revision=state.revision,
                phase=episode.phase,
                can_act=episode.phase not in ("complete", "allure", "ended")
                and viewer.user_id == controller
                and self._can_act(c, viewer),
                proposal=proposal,
                selected=episode.asset,
                assets=[
                    dict(id=x.id, name=x.name)
                    for x in rules.girl_assets(state, episode.actor)
                    if not x.void
                ],
                allure=episode.allure,
                assigned_frame=None,
                state=row["state"],
            )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        work: str,
        revision: int,
        name: str,
        description: str,
        evidence: str,
        *,
        damaged: bool,
        weapon: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, _, episode = self._owned(c, viewer, work, write=True, role="patient")
            if state.revision != revision or type(damaged) is not bool or type(weapon) is not bool:
                raise WorkflowError("STALE_ASSET_FACTS: refresh the exact actual original source.")
            event, identity = str(uuid4()), str(uuid4())
            proposal = ExistingAsset(
                id=identity,
                name=name.strip(),
                description=description.strip(),
                evidence=evidence.strip(),
                damaged=damaged,
                weapon=weapon,
                proposal_event=event,
            )
            changed = rules.propose(state, episode.id, proposal)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_girl_asset_proposed",
                changed,
                event_id=event,
                work_id=work,
                proposal_id=identity,
            )
            return dict(id=work, phase="review")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_girl_asset_proposed",
                dict(
                    work=work,
                    revision=revision,
                    name=name,
                    description=description,
                    evidence=evidence,
                    damaged=damaged,
                    weapon=weapon,
                ),
                operation,
                authorize=lambda c: self._authorize(c, viewer, work),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def review(
        self, viewer: GuildViewer, key: str, work: str, revision: int, *, allow: bool, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, _, episode = self._owned(c, viewer, work, write=True, role="judge")
            if state.revision != revision or type(allow) is not bool:
                raise WorkflowError(
                    "STALE_ASSET_REVIEW: refresh the actual existing-Asset proposal."
                )
            event = str(uuid4())
            changed = rules.review(state, episode.id, event, allow=allow, account=account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_girl_asset_reviewed",
                changed,
                event_id=event,
                work_id=work,
                proposal_id=episode.proposals[-1].id,
                accepted=allow,
            )
            return dict(id=work, phase="asset" if allow else "facts")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_girl_asset_reviewed",
                dict(work=work, revision=revision, allow=allow, account=account),
                operation,
                authorize=lambda c: self._authorize(c, viewer, work),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def select(
        self, viewer: GuildViewer, key: str, work: str, revision: int, asset: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, _, episode = self._owned(c, viewer, work, write=True, role="caster")
            if state.revision != revision:
                raise WorkflowError("STALE_VOID_TARGET: refresh the actual counterpart Asset list.")
            from girlframe.services.m3_items import prove_item

            items = [x for x in state.held_items if x.asset_id == asset]
            if len(items) != 1:
                raise WorkflowError("Recover the sole actual held Asset authority.")
            prove_item(c, self.game, state, items[0].id)
            event = str(uuid4())
            changed = rules.select_asset(state, episode.id, asset, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_girl_void_selected",
                changed,
                event_id=event,
                work_id=work,
                asset_id=asset,
            )
            return dict(id=work, phase="rewrite")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_girl_void_selected",
                dict(work=work, revision=revision, asset=asset),
                operation,
                authorize=lambda c: self._authorize(c, viewer, work),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def rewrite(
        self, viewer: GuildViewer, key: str, work: str, revision: int, description: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, row, episode = self._owned(c, viewer, work, write=True, role="patient")
            if state.revision != revision or not episode.asset:
                raise WorkflowError(
                    "STALE_VOID_REWRITE: recover the original caster's actual selection."
                )
            event = str(uuid4())
            changed = rules.corrupt(state, episode.id, episode.asset, description, event)
            current = next(x for x in changed.handler_girl_void if x.id == episode.id)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_girl_void_rewritten",
                changed,
                event_id=event,
                work_id=work,
                asset_id=episode.asset,
            )
            _complete(self.game, c, row, current, event, viewer, key)
            return dict(id=work, phase=current.phase, allure=current.allure, assigned_frame=None)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_girl_void_rewritten",
                dict(work=work, revision=revision, description=description),
                operation,
                authorize=lambda c: self._authorize(c, viewer, work),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def _complete(
    game: "GameService",
    c: Connection,
    row: dict[str, Any],
    episode: HandlerGirlVoid,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    if row["state"] == "resolved":
        return
    table = t.m3["m3_required_work"]
    body = json.loads(row["body_json"]) | dict(handler_girl_void=episode.id, completion_event=event)
    c.execute(
        table.insert().values(
            **(
                row
                | dict(
                    revision=row["revision"] + 1,
                    event_id=event,
                    state="resolved",
                    body_json=json.dumps(body, sort_keys=True),
                )
            )
        )
    )
    from girlframe.services.m3_mockingbird_void import complete_handler_girl_void

    complete_handler_girl_void(game, c, row["id"], event, viewer, key)


def completed_effect(game: "GameService", c: Connection, work: str, event: str) -> HandlerGirlVoid:
    _, row, episode = _source(c, game, work)
    proof = _snapshot(c, game, event)
    actual = (
        next((x for x in proof.handler_girl_void if x.id == episode.id), None) if proof else None
    )
    body = json.loads(row["body_json"])
    if (
        row["state"] != "resolved"
        or body.get("handler_girl_void") != episode.id
        or body.get("completion_event") != event
        or actual is None
        or not (
            actual.phase in ("complete", "allure")
            and actual.corruption_event == event
            or actual.phase == "ended"
            and actual.ended_event == event
        )
        or actual.assigned_frame is not None
    ):
        raise WorkflowError(
            "Only the actual original body/source Asset effect completes this Void consequence."
        )
    assert proof is not None
    if actual.phase == "ended":
        from girlframe.engine.m3_handler_consequences import body_original

        original_body = body_original(proof, actual.actor)
        if not any(
            x.body == original_body
            and x.ending == "death"
            and not x.alive
            and x.source_event == event
            for x in proof.handler_archives
        ):
            raise WorkflowError("A role change cannot replace the actual original body's death.")
    elif actual.asset is not None:
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            )
            .mappings()
            .first()
        )
        selected = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == actual.asset_choice_event,
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(audit["payload_json"]) if audit else {}
        chosen_payload = json.loads(selected["payload_json"]) if selected else {}
        if (
            audit is None
            or audit["kind"] != "m3.handler_girl_void_rewritten"
            or audit["actor_id"] != str(actual.controller)
            or payload.get("work_id") != work
            or payload.get("asset_id") != actual.asset
            or selected is None
            or selected["kind"] != "m3.handler_girl_void_selected"
            or selected["actor_id"] != str(actual.caster_controller)
            or chosen_payload.get("work_id") != work
            or chosen_payload.get("asset_id") != actual.asset
        ):
            raise WorkflowError(
                "The actual caster's selection and patient's rewrite must own this effect."
            )
        from girlframe.engine.m3_items import actual_asset, same_holder

        items = [
            x
            for x in proof.held_items
            if x.asset_id == actual.asset
            and same_holder(proof, x.holder, actual.actor)
            and x.location_mode == "carried"
        ]
        changed = actual_asset(proof, items[0]) if len(items) == 1 else None
        if (
            changed is None
            or not changed.void
            or changed.description != actual.rewrite
            or items[0].state_event != event
        ):
            raise WorkflowError(
                "A completion label cannot replace the actual sole Item Asset mutation."
            )
    else:
        values = rules.girl_assets(proof, actual.actor)
        if not values or not all(x.void for x in values) or actual.source_event != event:
            raise WorkflowError("Only actual nonempty already-Void source Assets coalesce allure.")
    return actual


def finish_initial_allure(
    game: "GameService",
    c: Connection,
    work: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    state, row, episode = _source(c, game, work)
    proof = _snapshot(c, game, event)
    original = (
        next((x for x in proof.handler_girl_void if x.id == episode.id), None) if proof else None
    )
    if (
        original is None
        or original.phase != "allure"
        or original.source_event != event
        or original.corruption_event != event
        or original.assigned_frame is not None
        or episode.id != original.id
        or not proof
    ):
        raise WorkflowError(
            "Only the actual preexisting nonempty all-Void source coalesces this allure."
        )
    values = rules.girl_assets(proof, original.actor)
    if not values or not all(x.void for x in values):
        raise WorkflowError("An empty or unknown Asset set is never treated as already all Void.")
    from girlframe.services.m3_items import prove_item

    for item in state.held_items:
        if item.asset_id in {x.id for x in values}:
            prove_item(c, game, state, item.id)
    _complete(game, c, row, episode, event, viewer, key)


def synchronize_endings(
    game: "GameService",
    c: Connection,
    event: str,
    viewer: GuildViewer | None = None,
    key: str | None = None,
) -> None:
    from girlframe.services.m3_harpy_defeat import ended_actor_source

    proof = _snapshot(c, game, event)
    if proof is None:
        raise WorkflowError(
            "Commit the actual original Handler body ending before its source cleanup."
        )
    for episode in proof.handler_girl_void:
        if episode.phase != "ended" or episode.ended_event != event:
            continue
        if ended_actor_source(game, c, proof, episode.actor) != event:
            raise WorkflowError(
                "No successor or context exit may impersonate actual original death."
            )
        _, row, _ = _source(c, game, episode.work)
        if row["state"] != "resolved":
            _complete(game, c, row, episode, event, viewer, key or event)
